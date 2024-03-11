// Listening for form submission
document.getElementById('configForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    // const audio = document.getElementById('audio').value;

    const codec = document.getElementById('format').value;
    const duration = document.getElementById('length').value;

    // Sending settings to the server
    fetch('/set-parameters', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ codec_selected: codec, recording_duration: duration }),
    })
    .then(response => response.json())
    .then(data => console.log(data))
    .catch(error => console.error('Error:', error));
});

// Function to retrieve available videos
function fetchVideoList() {
    fetch('/thumbnails')
        .then(response => response.json())
        .then(files => {
            const gallery = document.getElementById('videoGallery');
            gallery.innerHTML = ''; 
            files.forEach(file => {
                const videoFilename = getVideoFromThumbnail(file);
                const videoPath = `../videos/${videoFilename}`;
                const thumbnailPath = `../thumbnails/${file}`;
                const thumbnail = document.createElement('img');
                thumbnail.src = thumbnailPath;
                thumbnail.alt = 'Video Thumbnail';
                thumbnail.style.cursor = 'pointer';
                thumbnail.onclick = () => playVideo(videoPath);

                gallery.appendChild(thumbnail);
            });
        })
        .catch(error => console.error('Error fetching thumbnails:', error));
}

// Manipulating thumbnail url to get video url
function getVideoFromThumbnail(thumbnailPath) {
    return thumbnailPath.replace('_thumbnail.jpg', '.mp4');
}

// Playing the selected video
function playVideo(videoPath) {
    var videoPlayer = document.getElementById('videoPlayback');
    videoPlayer.src = videoPath;
    videoPlayer.load();
    fetchMetadata(videoPath)
    videoPlayer.play();
}

// Getting the selected video's metadata
function fetchMetadata(videoPath) {
    // Extracting the filename from the video url
    const filename = videoPath.split('/').pop().split('?')[0];
    
    fetch(`/get-metadata?videoUrl=${encodeURIComponent(videoPath)}`)
    .then(response => response.json())
    .then(data => {
        const metadataDiv = document.getElementById('videoMetadata');
        // Setting video title with the clip's filename
        metadataDiv.innerHTML = `<h3>Metadata for ${filename}:</h3>`; 
        // Showing the rest of the metadata
        metadataDiv.innerHTML += `Date: ${data.date}, Size: ${data.size}, Location: ${data.location}, Codec: ${data.codecMeta}`;
    })
    .catch(error => console.error('Error:', error));
}

// Refreshing the video list
document.addEventListener('DOMContentLoaded', (event) => {
    fetchVideoList();
});

// SocketIO for communication
var socket = io();

// Displaying the alert to the user
socket.on('alert', function(message) {
    alert(message);

    const parts = message.split('\n');
    const filename = parts[parts.length - 1].trim();
    const videoPath = `${filename}`;

    fetchVideoList();
    playVideo(videoPath);
});

// Function to delete videos on request
function deleteCurrentVideo() {
    const videoPlayer = document.getElementById('videoPlayback');
    const currentVideoPath = videoPlayer.src.split('/').pop();

    fetch('/delete-video', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ filename: currentVideoPath }),
    })
    .then(response => response.json())
    .then(data => {
        console.log(data.message);
        // Refreshing video list after deletion
        fetchVideoList();
    })
    .catch(error => console.error('Error:', error));
}

// Adding a listener to see if unsupported codec is selected
document.getElementById('videoPlayback').addEventListener('error', (e) => {
    const videoElement = e.target;
    if (videoElement.networkState === HTMLMediaElement.NETWORK_NO_SOURCE) {
        alert("This video format is not supported by your browser.\nPlease select a new Video Codec below.");
    }
});
