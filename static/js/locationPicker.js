// locationPicker.js - Location modal and map functionality
// Global variables
let map = null;
let marker = null;
let selectedCoords = null;
let locationMode = null;

function openLocationModal() {
    document.getElementById('locationModal').classList.add('show');
    document.getElementById('loading').classList.add('show');
    
    setTimeout(() => {
        document.getElementById('loading').classList.remove('show');
    }, 500);
}

function closeLocationModal() {
    document.getElementById('locationModal').classList.remove('show');
    if (map) {
        map.remove();
        map = null;
        marker = null;
    }
    selectedCoords = null;
    locationMode = null;
    document.getElementById('map').classList.remove('show');
    document.getElementById('searchContainer').classList.remove('show');
    document.getElementById('coordinatesDisplay').classList.remove('show');
    document.getElementById('saveLocationBtn').disabled = true;
    document.querySelectorAll('.location-option').forEach(opt => opt.classList.remove('active'));
}

function selectLocationMode(mode) {
    locationMode = mode;
    document.querySelectorAll('.location-option').forEach(opt => opt.classList.remove('active'));
    event.target.closest('.location-option').classList.add('active');
    
    document.getElementById('loading').classList.add('show');
    
    setTimeout(() => {
        document.getElementById('loading').classList.remove('show');
        document.getElementById('map').classList.add('show');
        
        if (mode === 'choose') {
            document.getElementById('searchContainer').classList.add('show');
        }
        
        initMap(mode);
    }, 500);
}

function initMap(mode) {
    if (!map) {
        // Default to Bhubaneswar
        const defaultCenter = [20.2961, 85.8245];
        
        map = L.map('map').setView(defaultCenter, 13);
        
        // Satellite imagery from Esri
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
            maxZoom: 19
        }).addTo(map);
        
        // Optional: Add labels overlay on top of satellite
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
            attribution: '',
            maxZoom: 19
        }).addTo(map);

        // Add click handler for choosing location
        if (mode === 'choose') {
            map.on('click', function(e) {
                updateMarker(e.latlng.lat, e.latlng.lng);
            });
        }
    }

    if (mode === 'current') {
        getCurrentLocation();
    }
}

function getCurrentLocation() {
    document.getElementById('loading').classList.add('show');
    
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const lat = position.coords.latitude;
                const lng = position.coords.longitude;
                
                map.setView([lat, lng], 15);
                updateMarker(lat, lng);
                
                document.getElementById('loading').classList.remove('show');
            },
            (error) => {
                console.error('Geolocation error:', error);
                alert('Unable to get current location. Please choose manually.');
                document.getElementById('loading').classList.remove('show');
            }
        );
    } else {
        alert('Geolocation is not supported by your browser.');
        document.getElementById('loading').classList.remove('show');
    }
}

function updateMarker(lat, lng) {
    if (marker) {
        map.removeLayer(marker);
    }

    marker = L.marker([lat, lng]).addTo(map);
    selectedCoords = { lat, lng };

    document.getElementById('coordinatesDisplay').classList.add('show');
    document.getElementById('coordsText').textContent = `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
    document.getElementById('saveLocationBtn').disabled = false;

    // Reverse geocoding
    reverseGeocode(lat, lng);
}

async function reverseGeocode(lat, lng) {
    try {
        const response = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`
        );
        const data = await response.json();
        if (data.display_name) {
            document.getElementById('searchInput').value = data.display_name;
        }
    } catch (error) {
        console.error('Reverse geocoding error:', error);
    }
}

async function searchLocation() {
    const query = document.getElementById('searchInput').value.trim();
    if (!query) return;

    document.getElementById('loading').classList.add('show');

    try {
        const response = await fetch(
            `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}`
        );
        const data = await response.json();

        if (data && data.length > 0) {
            const lat = parseFloat(data[0].lat);
            const lng = parseFloat(data[0].lon);
            
            map.setView([lat, lng], 15);
            updateMarker(lat, lng);
        } else {
            alert('Location not found. Please try a different search.');
        }
    } catch (error) {
        console.error('Search error:', error);
        alert('Search failed. Please try again.');
    } finally {
        document.getElementById('loading').classList.remove('show');
    }
}

function saveLocation() {
    if (selectedCoords) {
        const locationString = `${selectedCoords.lat.toFixed(6)}, ${selectedCoords.lng.toFixed(6)}`;
        document.getElementById('location').value = locationString;
        document.getElementById('location_lat').value = selectedCoords.lat;
        document.getElementById('location_lng').value = selectedCoords.lng;
        
        closeLocationModal();
    }
}