import os
import json
import time
import asyncio
import threading
import requests
from lucidclaw.core.bus import task_queue


def _load_dotenv_once():
    from dotenv import load_dotenv
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(project_root, ".env")
    load_dotenv(env_path, override=False)


_last_msg_id: str = ""
_last_chat_id: str = ""
_ctx_lock = threading.Lock()


def _get_tenant_token() -> str:
    now = time.time()
    if _get_tenant_token._ts and now - _get_tenant_token._ts < 7000:
        return _get_tenant_token._val
    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        return ""
    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10
        )
        token = resp.json().get("tenant_access_token", "")
        _get_tenant_token._val = token
        _get_tenant_token._ts = now
        return token
    except Exception:
        return ""

_get_tenant_token._val = ""
_get_tenant_token._ts = 0


def send_to_feishu(text: str) -> bool:
    """通过飞书 API 回复最近一条收到的消息"""
    with _ctx_lock:
        msg_id = _last_msg_id

    token = _get_tenant_token()
    if not token or not msg_id:
        return False
    try:
        content = json.dumps({"text": text})
        resp = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{msg_id}/reply",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json={"content": content, "msg_type": "text"},
            timeout=10
        )
        if not resp.ok:
            print(f" [飞书API错误] HTTP {resp.status_code}: {resp.text[:300]}")
        else:
            print(f" [飞书API] 回复成功")
        return resp.ok
    except Exception:
        return False


async def feishu_worker():
    _load_dotenv_once()

    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")

    if not app_id or not app_secret:
        print("[警告] 未配置 FEISHU_APP_ID / FEISHU_APP_SECRET，飞书监听未启动")
        return

    print(" [OK] 飞书监听已启动，等待群消息...")

    try:
        from lark_oapi.ws import Client as LarkWSClient
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
    except ImportError:
        print("[飞书错误] 请安装 lark-oapi: pip install lark-oapi")
        return

    loop = asyncio.get_running_loop()
    running = True

    def on_message(event):
        try:
            msg = event.event.message
            if msg.message_type != "text":
                return
            content = json.loads(msg.content)
            text = content.get("text", "")
            if not text:
                return
            with _ctx_lock:
                global _last_msg_id, _last_chat_id
                _last_msg_id = msg.message_id
                _last_chat_id = msg.chat_id
            asyncio.run_coroutine_threadsafe(
                task_queue.put(f"[飞书] {text}"), loop
            )
        except Exception as e:
            import traceback
            print(f" [飞书错误] {e}")
            traceback.print_exc()

    handler = (
        EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )

    def run_ws():
        ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(ws_loop)
        import lark_oapi.ws.client as ws_client_module
        ws_client_module.loop = ws_loop

        client = LarkWSClient(
            app_id, app_secret,
            event_handler=handler,
            auto_reconnect=True,
        )
        try:
            client.start()
        except Exception as e:
            if running:
                print(f" [飞书错误] WebSocket 断开: {e}")

    ws_thread = threading.Thread(target=run_ws, daemon=True, name="feishu-ws")
    ws_thread.start()

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        running = False
        print(" [飞书] 监听已停止")
