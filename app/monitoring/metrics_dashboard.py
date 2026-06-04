import gradio as gr
import requests


def fetch_metrics():
    try:
        resp = requests.get("http://localhost:8000/metrics")
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        return f"Error fetching metrics: {e}"


def dashboard():
    with gr.Blocks() as demo:
        gr.Markdown("# Monster Resort Concierge Metrics Dashboard")
        metrics_box = gr.Textbox(label="Prometheus Metrics", lines=20)
        refresh_btn = gr.Button("Refresh Metrics")
        refresh_btn.click(fn=fetch_metrics, outputs=metrics_box)
        # Auto-load on start
        demo.load(fetch_metrics, None, metrics_box)
    return demo


if __name__ == "__main__":
    dashboard().launch()
