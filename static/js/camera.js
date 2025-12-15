let cameraStream = null;
let capturedImageData = null;
let cropBoxElement = null;
let isDragging = false;
let isResizing = false;
let startX, startY, startLeft, startTop, startWidth, startHeight;
let resizeHandle = null;

async function openCameraModal() {
    document.getElementById('cameraModal').classList.add('show');
    
    try {
        const constraints = {
            video: {
                facingMode: 'environment',
                width: { ideal: 1920 },
                height: { ideal: 1080 }
            }
        };
        
        cameraStream = await navigator.mediaDevices.getUserMedia(constraints);
        document.getElementById('cameraStream').srcObject = cameraStream;
        
        // Reset UI
        document.getElementById('cameraView').style.display = 'block';
        document.getElementById('cropView').style.display = 'none';
        document.getElementById('captureBtn').style.display = 'inline-block';
        document.getElementById('retakeBtn').style.display = 'none';
        document.getElementById('cropBtn').style.display = 'none';
        document.getElementById('cameraInstruction').textContent = 'Position the receipt within the frame and click capture';
        
    } catch (error) {
        console.error('Camera error:', error);
        alert('Unable to access camera. Please check permissions or use file upload instead.');
        closeCameraModal();
    }
}

function closeCameraModal() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
        cameraStream = null;
    }
    document.getElementById('cameraModal').classList.remove('show');
    capturedImageData = null;
}

function capturePhoto() {
    const video = document.getElementById('cameraStream');
    const canvas = document.getElementById('captureCanvas');
    const ctx = canvas.getContext('2d');
    
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    // Stop camera
    if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
    }
    
    // Show crop interface
    document.getElementById('cameraView').style.display = 'none';
    document.getElementById('cropView').style.display = 'block';
    document.getElementById('captureBtn').style.display = 'none';
    document.getElementById('retakeBtn').style.display = 'inline-block';
    document.getElementById('cropBtn').style.display = 'inline-block';
    
    // Update instruction based on device
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    document.getElementById('cameraInstruction').textContent = isMobile 
        ? 'Use your finger to drag corners and adjust crop area, then click Crop & Save'
        : 'Drag the corners to adjust crop area, then click Crop & Save';
    
    // Auto-detect and crop receipt
    autoDetectReceipt(canvas);
}

function autoDetectReceipt(sourceCanvas) {
    const cropCanvas = document.getElementById('cropCanvas');
    const ctx = cropCanvas.getContext('2d');
    
    // Draw image to crop canvas
    cropCanvas.width = sourceCanvas.width;
    cropCanvas.height = sourceCanvas.height;
    ctx.drawImage(sourceCanvas, 0, 0);
    
    // Simple edge detection - find bright rectangular area
    const imageData = ctx.getImageData(0, 0, cropCanvas.width, cropCanvas.height);
    const detected = detectBrightRectangle(imageData);
    
    // Initialize crop box
    cropBoxElement = document.getElementById('cropBox');
    
    if (detected) {
        // Use detected area
        cropBoxElement.style.left = detected.x + 'px';
        cropBoxElement.style.top = detected.y + 'px';
        cropBoxElement.style.width = detected.width + 'px';
        cropBoxElement.style.height = detected.height + 'px';
    } else {
        // Default to 80% center crop
        const defaultWidth = cropCanvas.width * 0.8;
        const defaultHeight = cropCanvas.height * 0.8;
        const defaultX = (cropCanvas.width - defaultWidth) / 2;
        const defaultY = (cropCanvas.height - defaultHeight) / 2;
        
        cropBoxElement.style.left = defaultX + 'px';
        cropBoxElement.style.top = defaultY + 'px';
        cropBoxElement.style.width = defaultWidth + 'px';
        cropBoxElement.style.height = defaultHeight + 'px';
    }
    
    // Add drag and resize handlers for both mouse and touch
    setupCropHandlers();
}

function detectBrightRectangle(imageData) {
    const data = imageData.data;
    const width = imageData.width;
    const height = imageData.height;
    
    // Sample every 10th pixel for performance
    let minX = width, minY = height, maxX = 0, maxY = 0;
    let foundBright = false;
    
    for (let y = 0; y < height; y += 10) {
        for (let x = 0; x < width; x += 10) {
            const i = (y * width + x) * 4;
            const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3;
            
            // Detect bright areas (likely paper)
            if (brightness > 180) {
                foundBright = true;
                if (x < minX) minX = x;
                if (x > maxX) maxX = x;
                if (y < minY) minY = y;
                if (y > maxY) maxY = y;
            }
        }
    }
    
    if (foundBright && (maxX - minX) > 100 && (maxY - minY) > 100) {
        // Add 5% margin
        const margin = 20;
        return {
            x: Math.max(0, minX - margin),
            y: Math.max(0, minY - margin),
            width: Math.min(width - minX + margin, maxX - minX + margin * 2),
            height: Math.min(height - minY + margin, maxY - minY + margin * 2)
        };
    }
    
    return null;
}

function setupCropHandlers() {
    cropBoxElement = document.getElementById('cropBox');
    const handles = cropBoxElement.querySelectorAll('.resize-handle');
    
    // MOUSE EVENTS (Desktop)
    cropBoxElement.addEventListener('mousedown', startDrag);
    handles.forEach(handle => {
        handle.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            startResize(e, handle);
        });
    });
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', stopDragResize);
    
    // TOUCH EVENTS (Mobile)
    cropBoxElement.addEventListener('touchstart', startDragTouch, { passive: false });
    handles.forEach(handle => {
        handle.addEventListener('touchstart', (e) => {
            e.stopPropagation();
            startResizeTouch(e, handle);
        }, { passive: false });
    });
    document.addEventListener('touchmove', onTouchMove, { passive: false });
    document.addEventListener('touchend', stopDragResize);
    document.addEventListener('touchcancel', stopDragResize);
}

// MOUSE HANDLERS (Desktop)
function startDrag(e) {
    if (e.target.classList.contains('resize-handle')) return;
    
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    startLeft = parseInt(cropBoxElement.style.left);
    startTop = parseInt(cropBoxElement.style.top);
    e.preventDefault();
}

function startResize(e, handle) {
    isResizing = true;
    resizeHandle = handle;
    startX = e.clientX;
    startY = e.clientY;
    startLeft = parseInt(cropBoxElement.style.left);
    startTop = parseInt(cropBoxElement.style.top);
    startWidth = parseInt(cropBoxElement.style.width);
    startHeight = parseInt(cropBoxElement.style.height);
    e.preventDefault();
}

function onMouseMove(e) {
    if (isDragging) {
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        
        cropBoxElement.style.left = (startLeft + dx) + 'px';
        cropBoxElement.style.top = (startTop + dy) + 'px';
        e.preventDefault();
    }
    
    if (isResizing) {
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        
        updateCropBox(dx, dy);
        e.preventDefault();
    }
}

// TOUCH HANDLERS (Mobile)
function startDragTouch(e) {
    if (e.target.classList.contains('resize-handle')) return;
    
    isDragging = true;
    const touch = e.touches[0];
    startX = touch.clientX;
    startY = touch.clientY;
    startLeft = parseInt(cropBoxElement.style.left);
    startTop = parseInt(cropBoxElement.style.top);
    e.preventDefault();
}

function startResizeTouch(e, handle) {
    isResizing = true;
    resizeHandle = handle;
    const touch = e.touches[0];
    startX = touch.clientX;
    startY = touch.clientY;
    startLeft = parseInt(cropBoxElement.style.left);
    startTop = parseInt(cropBoxElement.style.top);
    startWidth = parseInt(cropBoxElement.style.width);
    startHeight = parseInt(cropBoxElement.style.height);
    e.preventDefault();
}

function onTouchMove(e) {
    if (!isDragging && !isResizing) return;
    
    const touch = e.touches[0];
    const dx = touch.clientX - startX;
    const dy = touch.clientY - startY;
    
    if (isDragging) {
        cropBoxElement.style.left = (startLeft + dx) + 'px';
        cropBoxElement.style.top = (startTop + dy) + 'px';
        e.preventDefault();
    }
    
    if (isResizing) {
        updateCropBox(dx, dy);
        e.preventDefault();
    }
}

// Shared resize logic for both mouse and touch
function updateCropBox(dx, dy) {
    const corner = resizeHandle.style.cursor || resizeHandle.dataset.corner;
    
    if (corner.includes('nw')) {
        cropBoxElement.style.left = (startLeft + dx) + 'px';
        cropBoxElement.style.top = (startTop + dy) + 'px';
        cropBoxElement.style.width = (startWidth - dx) + 'px';
        cropBoxElement.style.height = (startHeight - dy) + 'px';
    } else if (corner.includes('ne')) {
        cropBoxElement.style.top = (startTop + dy) + 'px';
        cropBoxElement.style.width = (startWidth + dx) + 'px';
        cropBoxElement.style.height = (startHeight - dy) + 'px';
    } else if (corner.includes('sw')) {
        cropBoxElement.style.left = (startLeft + dx) + 'px';
        cropBoxElement.style.width = (startWidth - dx) + 'px';
        cropBoxElement.style.height = (startHeight + dy) + 'px';
    } else if (corner.includes('se')) {
        cropBoxElement.style.width = (startWidth + dx) + 'px';
        cropBoxElement.style.height = (startHeight + dy) + 'px';
    }
}

function stopDragResize() {
    isDragging = false;
    isResizing = false;
    resizeHandle = null;
}

function applyCrop() {
    const sourceCanvas = document.getElementById('cropCanvas');
    const cropBox = document.getElementById('cropBox');
    
    const x = parseInt(cropBox.style.left);
    const y = parseInt(cropBox.style.top);
    const width = parseInt(cropBox.style.width);
    const height = parseInt(cropBox.style.height);
    
    // Create final cropped canvas
    const finalCanvas = document.createElement('canvas');
    finalCanvas.width = width;
    finalCanvas.height = height;
    const finalCtx = finalCanvas.getContext('2d');
    
    finalCtx.drawImage(sourceCanvas, x, y, width, height, 0, 0, width, height);
    
    // Convert to blob and create file
    finalCanvas.toBlob((blob) => {
        const file = new File([blob], 'captured_receipt.jpg', { type: 'image/jpeg' });
        
        // Create a DataTransfer to set the file input
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        document.getElementById('additional_receipt').files = dataTransfer.files;
        
        // Show preview
        const previewImg = document.getElementById('previewImg');
        previewImg.src = URL.createObjectURL(blob);
        document.getElementById('capturedImagePreview').style.display = 'block';
        
        closeCameraModal();
        alert('✅ Photo captured and cropped successfully!');
    }, 'image/jpeg', 0.9);
}

function retakePhoto() {
    openCameraModal();
}

function clearCapturedImage() {
    document.getElementById('additional_receipt').value = '';
    document.getElementById('capturedImagePreview').style.display = 'none';
}