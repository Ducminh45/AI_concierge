import requests
import sseclient


def stream_chat(session_id, message, api_url="http://localhost:8000/chat/stream"):
    payload = {"session_id": session_id, "message": message}
    with requests.post(api_url, json=payload, stream=True) as resp:
        client = sseclient.SSEClient(resp)
        for event in client.events():
            print(event.data)


if __name__ == "__main__":
    import sys

    session = "demo"
    msg = "What time is check in?" if len(sys.argv) < 2 else sys.argv[1]
    stream_chat(session, msg)
