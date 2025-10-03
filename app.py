import streamlit as st
from streamlit.components.v1 import html
from PIL import Image, ImageDraw, ImageFont
import requests, io, base64, datetime

st.set_page_config(page_title="GPS Map Camera", layout="centered")
st.title("📸 GPS Map Camera (Free - OSM)")

st.write("Upload or capture an image, fetch your location, and download it with GPS + address stamped.")

# -----------------------
# JS to request location
# -----------------------
GEO_JS = """
<script>
async function getGeo(){
  if (!navigator.geolocation){ alert('Geolocation not supported'); return; }
  navigator.geolocation.getCurrentPosition(
    function(pos){
      const val = pos.coords.latitude + ',' + pos.coords.longitude;
      let el = document.getElementById('streamlit_geo');
      if(!el){
        el = document.createElement('textarea');
        el.id = 'streamlit_geo';
        el.style = 'display:none';
        document.body.appendChild(el);
      }
      el.value = val;
      alert('Location detected: ' + val + '\\nCopy and paste into the Coordinates box.');
    },
    function(err){ alert('Geolocation error: ' + err.message); },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}
getGeo();
</script>
"""

# -----------------------
# Location input
# -----------------------
st.header("1) Location")
if st.button("📍 Fetch location"):
    html(GEO_JS, height=0)

coords_text = st.text_input("Coordinates (lat,lon)", placeholder="Paste here (e.g. 24.46196,72.77045)")
lat = lon = None
if coords_text:
    try:
        lat_s, lon_s = coords_text.split(",")
        lat, lon = float(lat_s.strip()), float(lon_s.strip())
        st.success(f"Location: {lat:.6f}, {lon:.6f}")
    except:
        st.error("Format must be: lat,lon")

# -----------------------
# Upload / capture photo
# -----------------------
st.header("2) Upload or capture an image")
uploaded = st.file_uploader("Upload an image (jpg/png)", type=["jpg","jpeg","png"])

CAM_HTML = """
<video id="video" width="320" height="240" autoplay></video>
<button id="snap">Capture</button>
<canvas id="canvas" width="320" height="240" style="display:none;"></canvas>
<script>
navigator.mediaDevices.getUserMedia({video:true}).then(s => {document.getElementById('video').srcObject = s;});
document.getElementById('snap').onclick = () => {
  const c = document.getElementById('canvas'), v = document.getElementById('video');
  c.getContext('2d').drawImage(v,0,0,c.width,c.height);
  const dataURL = c.toDataURL('image/jpeg');
  let el = document.getElementById('cam_data');
  if(!el){ el = document.createElement('textarea'); el.id='cam_data'; el.style='display:none'; document.body.appendChild(el); }
  el.value = dataURL;
  alert('Captured! Copy data URL and paste into the box in Streamlit.');
};
</script>
"""
html(CAM_HTML, height=280)

if st.button("Load captured image"):
    dataurl = st.text_area("Paste captured image data URL here")
    if dataurl:
        try:
            header, encoded = dataurl.split(",", 1)
            uploaded = io.BytesIO(base64.b64decode(encoded))
        except:
            st.error("Invalid data URL")

# -----------------------
# Helper functions for text size
# -----------------------
def text_height(font, text="Ag"):
    bbox = font.getbbox(text)
    return bbox[3] - bbox[1]

def text_width(font, text="Ag"):
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]

# -----------------------
# Generate stamped image
# -----------------------
st.header("3) Generate")
if st.button("Generate stamped photo"):
    if not uploaded:
        st.error("Upload or capture an image first.")
    elif lat is None or lon is None:
        st.error("Provide coordinates (paste from Fetch location).")
    else:
        # Open image
        img = Image.open(uploaded).convert("RGB")
        W, H = img.size

        # Reverse geocode
        address = ""
        try:
            r = requests.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"format": "jsonv2", "lat": lat, "lon": lon},
                headers={"User-Agent": "GPS-Map-Camera-Demo"},
                timeout=8,
            )
            address = r.json().get("display_name", "")
        except:
            address = ""

        # Static map inset
        map_img = None
        try:
            map_url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=16&size=160x160&markers={lat},{lon},red-pushpin"
            rr = requests.get(map_url, timeout=8)
            map_img = Image.open(io.BytesIO(rr.content)).convert("RGBA")
        except:
            pass

        # Prepare drawing
        out = img.convert("RGBA")
        draw = ImageDraw.Draw(out)
        try:
            font_big = ImageFont.truetype("DejaVuSans-Bold.ttf", max(20, W//25))
            font_small = ImageFont.truetype("DejaVuSans.ttf", max(14, W//45))
        except:
            font_big = ImageFont.load_default()
            font_small = ImageFont.load_default()

        now = datetime.datetime.now().strftime("%d/%m/%Y %I:%M %p")
        title = address if address else f"Lat {lat:.6f}, Lon {lon:.6f}"
        subtitle = f"Lat {lat:.6f}  Lon {lon:.6f}\n{now}"

        # Semi-transparent box at bottom
        box_h = int(H * 0.22)
        overlay = Image.new("RGBA", out.size, (0,0,0,0))
        ImageDraw.Draw(overlay).rectangle([0,H-box_h,W,H], fill=(0,0,0,180))
        out = Image.alpha_composite(out, overlay)
        draw = ImageDraw.Draw(out)

        # Draw title
        padding = 20
        draw.text((padding, H-box_h+padding), title, font=font_big, fill="white")

        # Draw subtitle lines
        y_sub = H - box_h + padding + (text_height(font_big, title) + 8)
        for i, line in enumerate(subtitle.split("\n")):
            draw.text((padding, y_sub + i*(text_height(font_small,line)+4)), line, font=font_small, fill="lightgray")

        # Paste map inset
        if map_img:
            thumb_w, thumb_h = map_img.size
            border = 4
            bg = Image.new("RGBA", (thumb_w+border*2, thumb_h+border*2), (255,255,255,255))
            bg.paste(map_img, (border,border), map_img)
            out.paste(bg, (12, H-box_h-thumb_h//2), bg)

        final = out.convert("RGB")

        # Show + download
        st.image(final, caption="Stamped image", use_column_width=True)
        buf = io.BytesIO()
        final.save(buf, format="JPEG", quality=92)
        b64 = base64.b64encode(buf.getvalue()).decode()
        st.markdown(f'<a href="data:file/jpg;base64,{b64}" download="stamped.jpg">⬇️ Download stamped image</a>', unsafe_allow_html=True)
