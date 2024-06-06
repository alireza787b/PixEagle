import cv2
import platform

def list_available_cameras(max_tested=10):
    """
    Lists all available USB cameras connected to the system across different platforms.
    The function tests up to a maximum specified number of camera indices.
    """
    # Initialize an empty list to store camera info
    camera_list = []

    # Identify the operating system to use appropriate settings
    system = platform.system()

    # Check each index up to max_tested to see if it corresponds to an active camera
    for device_index in range(max_tested):
        if system == "Windows":
            cap = cv2.VideoCapture(device_index, cv2.CAP_MSMF)  # Use Media Foundation on Windows
        else:
            cap = cv2.VideoCapture(device_index)  # Use default backend on Linux/Mac

        if cap.isOpened():
            # If the camera opens successfully, fetch and print some basic information
            camera_info = {
                'ID': device_index,
                'Resolution': f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}",
                'FPS': cap.get(cv2.CAP_PROP_FPS)
            }
            camera_list.append(camera_info)
            cap.release()
        else:
            # If a camera cannot be opened, release it and try the next one
            cap.release()

    return camera_list

# Get the list of available cameras
cameras = list_available_cameras()

# Print the list of cameras
if cameras:
    print("Available Cameras:")
    for camera in cameras:
        print(f"ID: {camera['ID']}, Resolution: {camera['Resolution']}, FPS: {camera['FPS']}")
else:
    print("No available USB cameras found.")
