import cv2
import datetime
import numpy as np
import os
import pyaudio
import socketio
import subprocess
import time
import wave
from multiprocessing import Process

# Setting variables
global audio_process
app_start_time = time.time()
codec_selected = 'x264'
cooldown_start_time = None
fourcc = cv2.VideoWriter_fourcc(*codec_selected)
motion_detected_time = None
motion_threshold = 5000  
out = None
recording = False
recording_cooldown = 10
recording_duration = 10
recording_in_progress = False

# Depricated
# audio_setting = 'yes'

# Scan for webcams and return name and resolution
for i in range(3): 
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        print(f"Webcam {i}: {cap.get(3)}x{cap.get(4)}")
        cap.release()

# Initialize default webcam
cap = cv2.VideoCapture(0)

# Check if the webcam opened correctly
if not cap.isOpened():
    raise IOError("Cannot open webcam")


# Depricated from changeover from JSON to SocketIO
# Load settings
# with open('settings.json', 'r') as f:
#     settings = json.load(f)

# Creating the background subtractor
fgbg = cv2.createBackgroundSubtractorMOG2(history=1000, varThreshold=10, detectShadows=True)

# Function to classify intruder size
def classify_movement_size(area, small_threshold=10000, large_threshold=100000):
    print(area)
    if area < small_threshold:
        return 'Small'
    elif area < large_threshold:
        return 'Medium'
    else:
        return 'Large'

# Function to determine location of intruder
def determine_side_of_screen(centroid, frame_width):
    return 'Left' if centroid[0] < frame_width / 2 else 'Right'

# Function to add metadata
def add_metadata_to_video(filename, camera_name="Default Camera", movement_size="", movement_side=""):
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    output_filename = filename.replace('audio.mp4', 'metadata.mp4')
    metadata_command = [
        "ffmpeg",
        "-i", filename,
        "-metadata", f"title=Intruder Detected!",
        "-metadata", f"comment=Camera: {camera_name}, Date: {date_str}, Movement: {movement_size}, Side: {movement_side}, Codec: {codec_selected}",
        "-codec", "copy",
        output_filename
    ]
    subprocess.run(metadata_command, shell=False)
    os.remove(filename)
    generate_thumbnail(output_filename)
    send_alert(output_filename)
    
# Function to send real-time alert
def send_alert(filename):   
    alert_date = filename
    parts = alert_date.replace('./videos/', '').split('_')
    alert_date = parts[0]
    alert_time = parts[1].split('.')[0]

    # Formatting the date and time
    date_formatted = f"{alert_date[:4]}-{alert_date[4:6]}-{alert_date[6:8]}"
    time_formatted = f"{alert_time[:2]}:{alert_time[2:4]}:{alert_time[4:6]}"

    alert_message = f'Intruder Detected!\n Date: {date_formatted}.\n Time: {time_formatted}.\nIntruder Size: {movement_size}, Intruder Location: {movement_side}\n{filename}'
    
    # Sending the alert message to the server
    sio.emit('motion_detected', {'message': alert_message})         

# Function to generate thumbnails
def generate_thumbnail(filename):
    thumbnail_directory = os.path.join(os.path.dirname(filename), "../thumbnails")
    os.makedirs(thumbnail_directory, exist_ok=True)
    thumbnail_path = os.path.join(thumbnail_directory, os.path.basename(filename).replace('.mp4', '_thumbnail.jpg'))

    # thumbnail_path = filename.replace('.mp4', '_thumbnail.jpg')
    thumbnail_command = [
        "ffmpeg",
        "-i", filename,
        "-ss", "00:00:01",
        "-vframes", "1",
        thumbnail_path
    ]
    subprocess.run(thumbnail_command, shell=False)

    return thumbnail_path

# Function to list audio devices - depricated
# def list_audio_devices():
#     p = pyaudio.PyAudio()
#     print("Available audio devices:")
#     for i in range(p.get_device_count()):
#         audio_devices = p.get_device_info_by_index(i)
#         print(f"{i}. {dev['name']} - Input Channels: {audio_devices['maxInputChannels']}")
#     p.terminate()
# list_audio_devices()

# Function to start recording audio
def start_audio_recording(audio_filename):
    try:
        print(f'Starting audio recording: {audio_filename}')
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100
        RECORD_SECONDS = recording_duration

        p = pyaudio.PyAudio()

        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        frames = []

        for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
            data = stream.read(CHUNK)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        p.terminate()

        wf = wave.open(audio_filename, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        print(f'Audio recording completed: {audio_filename}')
    except Exception as e:
        print(f"Error during audio recording: {e}")

# Function to merge audio and video clips
def merge_audio_video(video_filename, audio_filename):
    output_filename = video_filename.replace('.mp4', '_audio.mp4')
    
    audio_video_command = [
        "ffmpeg",
        "-i", video_filename,
        "-i", audio_filename,
        "-c:v", "copy",
        "-c:a", "aac",
        "-strict", "experimental",
        output_filename
    ]
    subprocess_result = subprocess.run(audio_video_command, shell=False)

    # Checking if subprocess call was successful before removing unneeded clips
    if subprocess_result.returncode == 0:
        os.remove(video_filename)
        os.remove(audio_filename)
        add_metadata_to_video(output_filename, camera_name="Default Camera", movement_size=movement_size, movement_side=movement_side)
    else:
        print(f"Error merging audio and video for {video_filename} and {audio_filename}")


# Reading the first video frame
ret, prev_frame = cap.read()
ret, prev_prev_frame = cap.read()

# Function to close popups
def close_popup(popup):
    global popup_open
    popup_open = False
    popup.destroy()

# Creating a SocketIO client
sio = socketio.Client()

# SocketIO Event to establish server connection
@sio.event
def connect():
    print("SocketIO connected to the server")

# SocketIO Event to reconfigure video settings
@sio.event
def reconfigure_video_settings(codec, duration):
    global out, codec_selected, recording_duration, fourcc
    codec_selected = codec
    recording_duration = duration
    # Print statement for debugging
    print(f'New recording duration: {recording_duration}')
    if codec_selected == 'x264':
        fourcc = cv2.VideoWriter_fourcc(*'X264')
    elif codec_selected == 'avc1':
        fourcc = cv2.VideoWriter_fourcc(*'AVC1')
    elif codec_selected == 'hevc':
        fourcc = cv2.VideoWriter_fourcc(*'HEVC')
    elif codec_selected == 'xvid':
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
    else:
        print("Unsupported codec. Defaulting to 'X264'.")
        fourcc = cv2.VideoWriter_fourcc(*'X264')
    if out is not None:
        # Release the current audio if it exists
        if audio_process and audio_process.is_alive():
            audio_process.terminate()
            audio_process.join()  
            print("Audio recording stopped early.")

        # Release the current video if it exists
        out.release()
        print("Video recording stopped early.")

# SocketIO Event to get video settings
@sio.event
def update_settings(data):
    print(f'Received new settings: {data}')
    reconfigure_video_settings(data['codec_selected'], int(data['recording_duration']))

# SocketIO Event to connect to the server
sio.connect('http://localhost:3000')

# Main function to keep searching for movement
while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Applying Gaussian blur to reduce noise
    blurred_frame = cv2.GaussianBlur(frame, (5, 5), 0)
    fgmask = fgbg.apply(blurred_frame)

    # Morphological operations to reduce noise
    # kernel = np.ones((5, 5), np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    fgmask = cv2.erode(fgmask, kernel, iterations=1)
    fgmask = cv2.dilate(fgmask, kernel, iterations=2)
    
    # Applying background subtraction and frame differencing
    diff1 = cv2.absdiff(frame, prev_frame)
    diff2 = cv2.absdiff(prev_frame, prev_prev_frame)

    frame_diff = cv2.bitwise_or(diff1, diff2)
    combined_mask = cv2.bitwise_and(fgmask, cv2.cvtColor(frame_diff, cv2.COLOR_BGR2GRAY))

    # Finding contours
    contours, _ = cv2.findContours(combined_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # Initialising motion detection
    motion_detected = False

    # Converting combined_mask to 3-channel
    combined_mask_color = cv2.cvtColor(combined_mask, cv2.COLOR_GRAY2BGR)


    # # Putting the frame and the grayscale mask side-by-side
    # combined_frame = np.hstack((frame, combined_mask_color))
   
    # Wait for 5 seconds after startup so history can be built
    if time.time() - app_start_time < 5:  
        continue

    # Motion detection logic
    if not recording and not (cooldown_start_time and time.time() - cooldown_start_time < recording_cooldown):
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > motion_threshold:
                contour_moment = cv2.moments(contour)
                if contour_moment["m00"] != 0:
                    centroid_x = int(contour_moment["m10"] / contour_moment["m00"])
                    centroid_y = int(contour_moment["m01"] / contour_moment["m00"])
                    centroid = (centroid_x, centroid_y)
                    # Drawing a green dot at the centroid
                    # cv2.circle(combined_mask_color, centroid, 50, (0, 255, 0), -1)
                frame_width = frame.shape[1]
                
                # Getting intruder size and location
                movement_size = classify_movement_size(area)
                movement_side = determine_side_of_screen(centroid, frame_width)
                
                # Setting time of detection to ensure noise isn't detected as movement
                if motion_detected_time is None:
                    motion_detected_time = time.time()
                elif time.time() - motion_detected_time >= 2:  # Motion detected for at least 2 seconds
                    motion_detected = True
                break

        # If motion is detected:
        if motion_detected and (motion_detected_time is None or time.time() - motion_detected_time >= 2):
            if motion_detected_time is None:
                motion_detected_time = time.time()
            elif time.time() - motion_detected_time >= 2:  # Ensures 2 seconds of continuous motion before starting to record
                if not recording:
                    # Start recording
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f'./videos/{timestamp}_intruder.mp4'
                    audio_filename = f'./audio/{timestamp}_intruder_audio.wav'
                    
                    # To run audio recording in a background thread
                    audio_process = Process(target=start_audio_recording, args=(audio_filename,))
                    audio_process.start()
                    print(f'audio should start')

                    # Running video recording
                    webcam_fps = cap.get(cv2.CAP_PROP_FPS)
                    out = cv2.VideoWriter(filename, fourcc, webcam_fps, (int(cap.get(3)), int(cap.get(4))))
                    recording = True

    elif recording:
        # Writing frame to recording
        # Embedding metadata into the frames
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame, f"Camera: Default - Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Intruder Detected!", (10, 30), font, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
        out.write(frame)
        if time.time() - motion_detected_time > recording_duration:
            # Stopping recording after 'recording_duration' seconds
            out.release()
            audio_process.join()
            
            # Merging clips
            merge_audio_video(filename, audio_filename)
            
            # Setting values to reset recording conditions
            recording = False
            cooldown_start_time = time.time()
            motion_detected_time = None 


    # Putting the frame and the grayscale mask side-by-side
    combined_frame = np.hstack((frame, combined_mask_color))

    # Showing the combined frame
    cv2.imshow('Frame', combined_frame)

    # Updating the frames for the next iteration
    prev_prev_frame = prev_frame
    prev_frame = frame.copy()

    # Exit motion detection when q is pressed
    if cv2.waitKey(10) == ord('q'):
        break

# Clean up for shut down
if out and recording:
    out.release()

cap.release()
cv2.destroyAllWindows()
