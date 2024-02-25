import cv2
import numpy as np
import socket
import struct

# Create a UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

server_address = ('172.21.148.30', 12345)  # Replace with your server IP and port

cap = cv2.VideoCapture(2)  # 0 for webcam

while True:
    ret, frame = cap.read()
    # Encode frame as jpg, reduce quality for smaller payload
    result, frame = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 30])
    # Convert to bytes
    data = frame.tobytes()

    # We send 65507 bytes which is the max in UDP
    if len(data) <= 65507:
        sock.sendto(data, server_address)
    else:
        print("Too large for UDP, decrease quality or resize image")

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
sock.close()
