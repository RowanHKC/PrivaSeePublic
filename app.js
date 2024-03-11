const express = require('express');
const { Server } = require("socket.io");
const http = require('http');
const { spawn } = require('child_process');
const { exec } = require('child_process');
const app = express();
const server = http.createServer(app);
const io = new Server(server);
const fs = require('fs');
const path = require('path');
const videosDir = path.join(__dirname, './videos');
const thumbnailsDir = path.join(__dirname, './thumbnails');

// Getting final video clips
app.get('/videos', (req, res) => {
    fs.readdir(videosDir, (err, files) => {
        if (err) {
            console.log(err);
            return res.status(500).send('Error retrieving video list.');
        }
        res.json(files);
    });
});

// Getting thumbnails
app.get('/thumbnails', (req, res) => {
    fs.readdir(thumbnailsDir, (err, files) => {
        if (err) {
            console.log(err);
            return res.status(500).send('Error retrieving thumbnail list.');
        }
        res.json(files);
    });
});

app.use(express.json());
app.use(express.static('public'));
app.use('/videos', express.static(path.join(__dirname, 'videos')));
app.use('/thumbnails', express.static(path.join(__dirname, 'thumbnails')));

// Listening for motion alerts from the Python
io.on('connection', (socket) => {
    console.log('User Connection Established');
    socket.on('motion_detected', (data) => {
        console.log('Motion detected:', data.message);
        // Broadcasting alert to all users
        io.emit('alert', data.message);
    });
});

// Starting Python
const motionDetection = spawn('python', ['privasee.py']);

motionDetection.stdout.on('data', (data) => {
    console.log(`stdout: ${data}`);
    io.emit('motion-detected', data.toString());
});

// Starting server
server.listen(3000, () => {
    console.log('Server is running on http://localhost:3000');
});


// Setting recording codec and duration
app.post('/set-parameters', (req, res) => {
    const { codec_selected = 'x264', recording_duration = 10 } = req.body;
    const settings = { codec_selected, recording_duration };
    // Writing to JSON - depricated
    fs.writeFileSync('settings.json', JSON.stringify(settings));

    // Sending an update_settings event to the Python
    io.emit('update_settings', settings);

    res.json({ status: 'Settings updated', ...settings });
});

// POST to delete videos on command
app.post('/delete-video', (req, res) => {
    const { filename } = req.body;
    const videoPath = `./videos/${filename}`;
    const thumbnailPath = `./thumbnails/${filename.replace('.mp4', '_thumbnail.jpg')}`;

    try {
        fs.unlinkSync(videoPath); 
        fs.unlinkSync(thumbnailPath); 
        res.json({ message: 'Video and thumbnail deleted successfully.' });
    } catch (error) {
        console.error(error);
        res.status(500).json({ message: 'Failed to delete video and thumbnail.' });
    }
});

// Getting vodeo metadata
app.get('/get-metadata', (req, res) => {
    let videoUrl = req.query.videoUrl;
    let pathParts = videoUrl.split('/').slice(1);
    videoUrl = pathParts.join('/');
    const videoPath = `${videoUrl}`;

    // Using ffmpeg's ffprobe to extract metadata from the video comments
    const command = `ffprobe -v error -show_entries format_tags=comment -of default=noprint_wrappers=1:nokey=1 "${videoPath}"`;

    exec(command, (error, stdout, stderr) => {
        if (error) {
            console.error(`exec error: ${error}`);
            return res.status(500).send('Error extracting metadata');
        }

        const metadata = stdout.trim().split(', ').reduce((acc, curr) => {
            const [key, value] = curr.split(': ');
            if (key.includes("Date")) acc["date"] = value;
            if (key.includes("Movement")) acc["size"] = value;
            if (key.includes("Side")) acc["location"] = value;
            if (key.includes("Codec")) acc["codecMeta"] = value;
            return acc;
        }, {});

        res.json(metadata);
    });
});
