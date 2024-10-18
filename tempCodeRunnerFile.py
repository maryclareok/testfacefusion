import requests
import websocket
import threading
import time
import json
import base64

# Update these paths to your local image files
image1_path = 'download.jpg'
image2_path = 'r3gyjq.jpg'

# Endpoint URLs
upload_url = 'https://u08436aqlqpu9q-3000.proxy.runpod.net/upload'
websocket_url = 'wss://u08436aqlqpu9q-3000.proxy.runpod.net/queue/join'

# Create a session to maintain cookies and session data
session = requests.Session()

# Function to upload images
def upload_images():
    print("Uploading images...")
    files = [
        ('files', open(image1_path, 'rb')),
        ('files', open(image2_path, 'rb'))
    ]
    # Use the same session to maintain cookies
    response = session.post(upload_url, files=files)
    if response.status_code == 200:
        print("Images uploaded successfully.")
    else:
        print(f"Error uploading images: {response.status_code} - {response.text}")

# WebSocket event handlers
def on_message(ws, message):
    print("Received a message:")
    try:
        data = json.loads(message)
        status = data.get('status')
        if status == 'processing':
            progress = data.get('progress', 0)
            print(f"Processing... {progress}% completed.")
        elif status == 'completed':
            fused_image_data = data.get('fused_image')
            if fused_image_data:
                # Decode and save the fused image
                fused_image = base64.b64decode(fused_image_data)
                fused_image_path = 'fused_image.jpg'  # Update the path if necessary
                with open(fused_image_path, 'wb') as f:
                    f.write(fused_image)
                print(f'Fused image saved to {fused_image_path}')
            else:
                print('No fused image data received.')
            ws.close()
        elif status == 'error':
            print(f"Error: {data.get('message')}")
            ws.close()
        else:
            print(f"Unknown status: {status}")
    except json.JSONDecodeError:
        print("Received non-JSON message:", message)

def on_error(ws, error):
    print("WebSocket error:", error)

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed.")

def on_open(ws):
    print("WebSocket connection opened.")
    # After the WebSocket connection is open, upload the images
    threading.Thread(target=upload_images).start()

if __name__ == "__main__":
    # Make an initial request to obtain session cookies
    session.get(upload_url)
    
    # Extract cookies from the session to pass to the WebSocket
    cookies = session.cookies.get_dict()
    cookie_header = '; '.join([f'{key}={value}' for key, value in cookies.items()])
    
    # Start the WebSocket connection
    websocket.enableTrace(False)
    ws_app = websocket.WebSocketApp(
        websocket_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        header={'Cookie': cookie_header}
    )
    
    # Run the WebSocket in a separate thread
    ws_thread = threading.Thread(target=ws_app.run_forever)
    ws_thread.daemon = True
    ws_thread.start()
    
    try:
        while ws_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        ws_app.close()
        print("Program terminated.")
