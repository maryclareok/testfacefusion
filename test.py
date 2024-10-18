import requests
import websocket
import threading
import time
import json
import base64
import os
import ssl
import uuid
import urllib.parse

# Paths to your local image files
image1_path = 'download.jpg'  # Replace with your first image file path
image2_path = 'r3gyjq.jpg'    # Replace with your second image file path

# Endpoint URLs
app_url = os.getenv('APP_URL')  # Replace with your actual app URL
websocket_url = os.getenv('WEBSOCKET_URL')  # Replace with your actual WebSocket URL

def main():
    # Create a session to maintain cookies and session data
    session = requests.Session()

    # Verify that image files exist
    if not os.path.isfile(image1_path):
        print(f"Image file {image1_path} does not exist.")
        exit()

    if not os.path.isfile(image2_path):
        print(f"Image file {image2_path} does not exist.")
        exit()

    # Make an initial request to obtain session cookies and IDs
    try:
        initial_response = session.get(app_url)
        if initial_response.status_code != 200:
            print(f"Initial request failed: {initial_response.status_code} - {initial_response.text}")
            exit()
    except Exception as e:
        print(f"An exception occurred during initial request: {e}")
        exit()

    # Extract cookies from the session to pass to the WebSocket
    cookies = session.cookies.get_dict()
    session_id = cookies.get('session_id', '')
    session_hash = cookies.get('session_hash', '')
    if not session_hash:
        print("No session_hash provided by the server.")
        # Optionally, proceed without session_hash or handle accordingly

    # Prepare the headers with cookies for the WebSocket connection
    cookie_header = '; '.join([f'{key}={value}' for key, value in cookies.items()])
    print(f"Cookie Header: {cookie_header}")

    # Define a flag to indicate when the process is completed
    process_completed = threading.Event()

    # Encode images in base64
    with open(image1_path, 'rb') as f:
        image1_data = f.read()
        image1_b64 = "data:image/jpeg;base64," + base64.b64encode(image1_data).decode('utf-8')

    with open(image2_path, 'rb') as f:
        image2_data = f.read()
        image2_b64 = "data:image/jpeg;base64," + base64.b64encode(image2_data).decode('utf-8')

    # WebSocket event handlers
    def on_message(ws, message):
        print("Received a message:")
        print(message)  # Raw message for debugging
        try:
            data = json.loads(message)
            print("Parsed message data:")
            print(json.dumps(data, indent=2))  # Pretty-print the parsed message
            msg_type = data.get('msg')

            if msg_type == 'send_hash':
                print("Received send_hash message.")
                # Send only the session_hash back to the server
                payload = {
                    "session_hash": session_hash,
                    "msg": "send_hash"
                }
                ws.send(json.dumps(payload))

            elif msg_type == 'estimation':
                # Received estimation of processing time
                rank_eta = data.get('rank_eta', 'unknown')
                queue_size = data.get('queue_size', 'unknown')
                print(f"Estimated time: {rank_eta}s, Queue size: {queue_size}")

            elif msg_type == 'send_data':
                print("Received send_data message.")
                # Prepare the data payload
                payload_data = [
                    image1_b64,  # First image
                    image2_b64,  # Second image
                    None         # Additional parameter (if any)
                ]
                payload = {
                    "session_hash": session_hash,
                    "data": payload_data,
                    "event_data": None,
                    "msg": "data"
                }
                print("Sending payload:")
                print(json.dumps(payload, indent=2))
                ws.send(json.dumps(payload))

            elif msg_type == 'process_starts':
                print("Process has started.")
                # Optionally, implement a timeout if needed

            elif msg_type == 'process_completed':
                print("Process completed.")
                output = data.get('output')
                success = data.get('success', False)
                if success:
                    output_data = output.get('data')
                    if output_data and len(output_data) > 0:
                        image_data = output_data[0]
                        # Handle data URL
                        if isinstance(image_data, str) and image_data.startswith("data:image"):
                            # Extract and decode the base64 data
                            header, encoded = image_data.split(",", 1)
                            image_bytes = base64.b64decode(encoded)
                            with open('fused_image.png', 'wb') as f:
                                f.write(image_bytes)
                            print('Fused image saved to fused_image.png')
                        else:
                            print("Unexpected output format.")
                    else:
                        print("No output data received.")
                else:
                    print("Server reported failure.")
                    if output and 'error' in output and output['error']:
                        print(f"Error from server: {output['error']}")
                    else:
                        print("No error message provided by server.")
                process_completed.set()
                ws.close()

            else:
                print(f"Received unexpected message type: {msg_type}")
                print("Full message data:", json.dumps(data, indent=2))

        except json.JSONDecodeError:
            print("Received non-JSON message:", message)

    def on_error(ws, error):
        print("WebSocket error:", error)
        process_completed.set()

    def on_close(ws, close_status_code, close_msg):
        print(f"WebSocket closed with status code: {close_status_code}, message: {close_msg}")
        process_completed.set()

    def on_open(ws):
        print("WebSocket connection opened.")

    # Start the WebSocket connection
    ws_app = websocket.WebSocketApp(
        websocket_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        header={'Cookie': cookie_header}
    )

    # Run the WebSocket in a separate thread
    ws_thread = threading.Thread(
        target=ws_app.run_forever,
        kwargs={
            "sslopt": {
                'cert_reqs': ssl.CERT_NONE  # In production, use ssl.CERT_REQUIRED
            }
        }
    )
    ws_thread.daemon = True
    ws_thread.start()

    # Wait for the process to complete
    try:
        while not process_completed.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        ws_app.close()
        print("Program terminated.")

if __name__ == "__main__":
    main()
