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

# Enable detailed WebSocket logs (optional, can be uncommented for debugging)
# websocket.enableTrace(True)

# Paths to your local image files
image1_path = 'download.jpg'  # Your first image file path
image2_path = 'r3gyjq.jpg'    # Your second image file path

# Endpoint URLs from environment variables
app_url = os.getenv('APP_URL')  # Load from .env
websocket_url = os.getenv('WEBSOCKET_URL')  # Load from .env

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
        # Generate a random session hash if not provided
        session_hash = str(uuid.uuid4()).replace("-", "")[:16]

    # Function index (fn_index) as determined from the web interface
    fn_index = 105  # Set to the correct fn_index

    # Prepare the headers with cookies for the WebSocket connection
    cookie_header = '; '.join([f'{key}={value}' for key, value in cookies.items()])
    print(f"Cookie Header: {cookie_header}")

    # Define a flag to indicate when the process is completed
    process_completed = threading.Event()

    # Define the process_timer variable before defining on_message
    process_timer = None

    # Encode images in base64
    with open(image1_path, 'rb') as f:
        image1_data = f.read()
        image1_b64 = "data:image/jpeg;base64," + base64.b64encode(image1_data).decode('utf-8')

    with open(image2_path, 'rb') as f:
        image2_data = f.read()
        image2_b64 = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode('utf-8')

    # Define a timeout value (e.g., 60 seconds)
    PROCESS_TIMEOUT = 60  # Adjust as needed

    # WebSocket event handlers
    def on_message(ws, message):
        nonlocal process_timer
        print("Received a message:")
        # Optionally save the message to a file for debugging
        # with open('response.json', 'w') as f:
        #     f.write(message)
        try:
            data = json.loads(message)
            msg_type = data.get('msg')

            if msg_type == 'send_hash':
                print("Received send_hash message.")
                # Send the session hash back to the server
                ws.send(json.dumps({
                    "session_hash": session_hash,
                    "fn_index": fn_index,
                    "session_id": session_id,
                    "msg": "send_hash"
                }))

            elif msg_type == 'estimation':
                # Received estimation of processing time
                rank_eta = data.get('rank_eta', 'unknown')
                queue_size = data.get('queue_size', 'unknown')
                print(f"Estimated time: {rank_eta}s, Queue size: {queue_size}")

            elif msg_type == 'send_data':
                print("Received send_data message.")
                # Adjust the data payload as per the server's expected format
                payload_data = [
                    image1_b64,  # First image
                    image2_b64,  # Second image
                    None         # Additional parameter (if any)
                ]
                payload = {
                    "fn_index": fn_index,
                    "data": payload_data,
                    "event_data": None,
                    "session_hash": session_hash,
                    "session_id": session_id,
                    "msg": "data"
                }
                ws.send(json.dumps(payload))

            elif msg_type == 'process_starts':
                print("Process has started.")
                # Start a timer to detect if the process takes too long
                process_timer = threading.Timer(PROCESS_TIMEOUT, on_process_timeout, args=(ws,))
                process_timer.start()

            elif msg_type == 'process_completed':
                print("Process completed.")
                # Cancel the timer since the process completed
                if process_timer:
                    process_timer.cancel()
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
                        # Handle file path
                        elif isinstance(image_data, dict):
                            # Depending on the server response, adjust the parsing
                            if image_data.get('__type__') == 'update':
                                value = image_data.get('value')
                                if isinstance(value, list) and len(value) > 0:
                                    file_info = value[0]
                                    file_name = file_info.get('name')
                                else:
                                    print("No file information found in 'value'.")
                                    file_name = None
                            else:
                                file_name = image_data.get('name')

                            if file_name:
                                # Construct the file URL
                                base_url = app_url.rstrip('/')
                                encoded_file_name = urllib.parse.quote(file_name)
                                file_url = f"{base_url}/file={encoded_file_name}"
                                print(f"Downloading image from {file_url}")
                                # Use the same session to download the file
                                response = session.get(file_url)
                                if response.status_code == 200:
                                    fused_image_path = 'fused_image.png'  # Use the appropriate extension
                                    with open(fused_image_path, 'wb') as f:
                                        f.write(response.content)
                                    print(f'Fused image saved to {fused_image_path}')
                                else:
                                    print(f"Failed to download image. Status code: {response.status_code}")
                            else:
                                print("File name not found in output.")
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

            elif msg_type == 'queue_full':
                print("The queue is full. Please try again later.")
                process_completed.set()
                ws.close()

            elif msg_type == 'error':
                error_message = data.get('error', 'Unknown error')
                print(f"Error from server: {error_message}")
                process_completed.set()
                ws.close()

            else:
                print(f"Received unexpected message type: {msg_type}")
                print("Full message data:", data)

        except json.JSONDecodeError:
            print("Received non-JSON message:", message)

    def on_error(ws, error):
        print("WebSocket error:", error)
        process_completed.set()

    def on_close(ws, close_status_code, close_msg):
        print(f"WebSocket closed with status code: {close_status_code}, message: {close_msg}")
        process_completed.set()

    def on_process_timeout(ws):
        print(f"Process did not complete within {PROCESS_TIMEOUT} seconds.")
        ws.close()
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
                'cert_reqs': ssl.CERT_NONE  # Use ssl.CERT_REQUIRED in production
            }
            # Removed 'max_size' parameter
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
