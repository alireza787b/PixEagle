import cv2
import subprocess

def list_available_cameras():
    """
    This function lists all available USB cameras connected to the system
    with their respective IDs and any accessible information.
    """
    # Try to fetch video device information using v4l2-ctl
    try:
        # Run v4l2-ctl to get device info
        result = subprocess.run(['v4l2-ctl', '--list-devices'], capture_output=True, text=True)
        devices_info = result.stdout
    except FileNotFoundError:
        print("v4l2-ctl not found. Please ensure it's installed and available on your path.")
        devices_info = ""

    # Initialize an empty list to store camera info
    camera_list = []

    # Split output into lines
    lines = devices_info.split('\n')

    # Process the lines
    device_name = None
    for line in lines:
        if line.endswith(' (usb-'):
            device_name = line.strip()
        elif '/dev/video' in line:
            if device_name:
                device_index = int(line.strip().split('/dev/video')[-1])
                # Use OpenCV to try to open the video capture
                # This checks if the device at the index is available for use
                cap = cv2.VideoCapture(device_index)
                if cap.isOpened():
                    cap.release()
                    # Append the device name and index to the list
                    camera_list.append((device_name, device_index))
                else:
                    print(f"Device /dev/video{device_index} could not be initialized.")

    return camera_list

# Get the list of available cameras
cameras = list_available_cameras()

# Print the list of cameras
if cameras:
    print("Available Cameras:")
    for name, index in cameras:
        print(f"{index}: {name}")
else:
    print("No available USB cameras found.")

