import os
import gradio as gr
import requests
from dotenv import load_dotenv

load_dotenv()

# --- CLEAN MINIMAL THEME ---
monster_theme = gr.themes.Soft(
    primary_hue="slate",
    secondary_hue="slate",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
).set(
    body_background_fill="#fafafa",
    block_background_fill="white",
    block_border_width="1px",
    button_primary_background_fill="#1a1a1a",
    button_primary_background_fill_hover="#000000",
    button_primary_text_color="white",
)

custom_css = """
footer {visibility: hidden}
.gradio-container {max-width: 900px !important; margin: auto;}
h1 {text-align: center; color: #1a1a1a; margin-bottom: 0; padding-top: 20px; font-weight: 600;}
p.subtitle {text-align: center; color: #6b7280; margin-bottom: 20px; font-size: 14px;}

/* Chat container */
.bubble-wrap {height: 500px !important; max-height: 500px !important;}
#chatbot {border-radius: 12px !important;}

/* Send button — dark style to match the design */
button.primary {
    background-color: #1a1a1a !important;
    border-radius: 8px !important;
}
"""


def predict(message, history, session_id):
    """
    Handle chat predictions with the Monster Resort Concierge API

    Args:
        message: User's input message
        history: Chat history in dictionary format
        session_id: Current session ID

    Returns:
        Tuple of (updated_history, cleared_message, new_session_id)
    """
    # Add user message immediately
    history.append({"role": "user", "content": message})

    # Add loading indicator
    history.append(
        {
            "role": "assistant",
            "content": "🕯️ The concierge is preparing your response...",
        }
    )

    # Yield the loading state so UI updates immediately
    yield history, "", session_id

    # Make the API call
    url = "http://127.0.0.1:8000/chat"
    headers = {
        "Authorization": f"Bearer {os.environ.get('MRC_API_KEY', 'your-api-key-here')}",
        "Content-Type": "application/json",
    }
    payload = {"message": message, "session_id": session_id}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        data = response.json()

        reply = data.get("reply", "The concierge is silent...")
        new_session_id = data.get("session_id", session_id)

        # Remove loading indicator and add actual response
        history = history[:-1]  # Remove loading message
        history.append({"role": "assistant", "content": reply})

        yield history, "", new_session_id

    except requests.exceptions.Timeout:
        # Handle timeout
        history = history[:-1]  # Remove loading message
        history.append(
            {
                "role": "assistant",
                "content": "⏱️ The concierge took too long to respond. Please try again.",
            }
        )
        yield history, "", session_id

    except requests.exceptions.ConnectionError:
        # Handle connection error
        history = history[:-1]  # Remove loading message
        history.append(
            {
                "role": "assistant",
                "content": "🔌 Cannot reach the concierge service. Please ensure the server is running.",
            }
        )
        yield history, "", session_id

    except Exception as e:
        # Handle other errors
        history = history[:-1]  # Remove loading message
        history.append(
            {
                "role": "assistant",
                "content": f"🌫️ The resort is lost in the mist: {str(e)}",
            }
        )
        yield history, "", session_id


# Build the Gradio interface
with gr.Blocks(theme=monster_theme, css=custom_css) as demo:
    gr.Markdown("# Monster Game Resort Concierge")
    gr.Markdown(
        "<p class='subtitle'>Your guide to the spookiest stays and eeriest experiences</p>",
        elem_classes="subtitle",
    )

    chatbot = gr.Chatbot(
        elem_id="chatbot",
        type="messages",
        height=500,
        show_copy_button=True,
        show_label=False,
        avatar_images=(None, None),
    )

    with gr.Row():
        msg = gr.Textbox(
            placeholder="Ask about rooms, amenities, or make a booking...",
            show_label=False,
            lines=1,
            max_lines=3,
            scale=5,
            container=False,
        )
        submit_btn = gr.Button("Send", variant="primary", scale=1)

    examples = gr.Examples(
        examples=[
            "How many monster properties can I stay at?",
            "Take me inside Vampire Manor — what rooms are there?",
            "What luxury treatments does the Mummy Resort spa offer?",
            "Tell me everything about the Full Moon Festival",
        ],
        inputs=msg,
        label="",
    )

    # Hidden state to track the session across turns
    session_id_state = gr.State(None)

    # Connect BOTH the textbox (Enter key) and button to the prediction function
    msg.submit(
        fn=predict,
        inputs=[msg, chatbot, session_id_state],
        outputs=[chatbot, msg, session_id_state],
    )

    submit_btn.click(
        fn=predict,
        inputs=[msg, chatbot, session_id_state],
        outputs=[chatbot, msg, session_id_state],
    )

# Launch the interface
if __name__ == "__main__":
    print("Starting Monster Game Resort Concierge UI...")
    print("📍 Access the interface at: http://localhost:7861")
    print("🔧 Make sure your FastAPI server is running on http://localhost:8000")
    demo.launch(server_port=7861, share=False, show_error=True, server_name="127.0.0.1")
