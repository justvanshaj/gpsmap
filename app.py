# app.py
import streamlit as st
from streamlit.components.v1 import html
from PIL import Image, ImageDraw, ImageFont
import requests, io, base64, datetime

st.set_page_config(page_title="Simple GPS Map Camera", layout="centered")
st.title("Simple GPS Map Camera (Free, OSM)")

st.markdown(
    "Upload or capture a photo, click **Fetch location** (allow the browser prompt), then click **Use detected coords** or paste coordinates into the box. Finally click **Generate** and download the stamped image."
)

# -----------------------
# Small JS: request geolocation and write to a hidden textarea
# -----------------------
GEO_JS = """
<script>
async function getGeo(){
  if (!navigator.geolocation){ alert('Geolocation not supported'); return; }
  navigator.geolocation.getCurrentPosition(
    function(pos){
      const val = pos.coords.latitude + ',' + pos.coords.longitude;
      // create or update a hidden textarea with id 'streamlit_geo'
      let el = document.getElementById('streamlit_geo');
      if(!el){
        el = document.createElement('textarea');
        el.id = 'streamlit_geo';
        el.style = 'display:none';
        document.body.appendChild(el);
      }
      el.value = val;
      // also show a small visible notice for user convenience
      let note = document.getElementById('geo_note_streamlit');
      if(!note){
        note = document.createElement('div');
        note.id = 'geo_note_streamlit';
        note.style = 'color:green; font-weight:bold; margin-top:6px';
        document.body.appendChild(note);
      }
      note.innerText = 'Location detected: ' + val + ' — click "Use detected coords" in the app.';
    },
    function(err){ alert('Geolocation error: ' + err.message); },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}
getGeo();
</script>
"""

# -----------------------
# UI: location fetch + coords input
# -----------------------
st.header("1) Location")
if st.button("📍 Fetch location (browser will ask permission)"):
    # inject JS to populate a hidden textarea on the page with coords
    html(GEO_JS, height=0)

st.write("If browser detection works you can click **Use detected coords** to copy them into the box. Otherwise paste `lat,lon` (e.g. `24.46196,72.77045`).")
col1, col2 = st.columns([1,1])
with col1:
    if st.button("Use detected coords"):
        # This attempts to read the hidden textarea by injecting JS that sets window.name,
        # then reading it via st.experimental_get_query_params is unreliable.
        # A simple pragmatic approach: re-render a small JS that copies the hidden textarea into a visible text input element created on the page,
        # then ask the user to copy it. But to keep the app simple, we will attempt a best-effort DOM-to-prompt copy:
        COPY_JS = """
        <script>
        let el = document.getElementById('streamlit_geo');
        if(el && el.value){
          // put value into a prompt so user can copy quickly (fallback)
          prompt('Detected coordinates (copy and paste into the app box):', el.value);
        } else {
          alert('No detected coordinates found — please click "Fetch location" first and allow permission.');
        }
        </script>
        """
        html(COPY_JS, height=0)
with col2:
    coords_text = st.text_input("Coordinates (lat,lon)", value="")

# parse coords
lat = lon = None
if coords_text:
    try:
        lat_s, lon_s = coords_text.split(",")
        lat = float(lat_s.strip()); lon = float(lon_s.strip())
    except:
        st.error("Could not parse coordinates. Use format: lat,lon")

# -----------------------
# Image upload or capture
# -----------------------
st.header("2) Upload or capture an image")
uploaded = st.file_uploader("Upload an image (jpg/png)", type=["jpg","jpeg","png"])

# small webcam capture snippet: captures to a hidden textarea 'cam_data' that user can paste into the app using "Load captured image"
CAM_HTML = """
<video id="video" width="320" height="240" autoplay></video>
<button id="snap">Capture</button>
<canvas id="canvas" width="320" height="240" style="display:none;"></canvas>
<script>
navigator.mediaDevices.getUserMedia({video:true}).then(s => {document.getElementById('video').srcObject = s;}).catch(e => {});
document.getElementById('snap').onclick = () => {
  const c = document.getElementById('canvas'), v = document.getElementById('video');
  c.getContext('2d').drawImage(v,0,0,c.width,c.height);
  const dataURL = c.toDataURL('image/jpeg');
  let el = document.getElementById('cam_data');
  if(!el){ el = document.createElement('textarea'); el.id='cam_data'; el.style='display:none'; document.body.appendChild(el); }
  el.value = dataURL;
  alert('Captured. Click "Load captured image" in the app and paste the dataURL if needed.');
};
</script>
"""
html(CAM_HTML, height=260)

if st.button("Load captured image"):
    dataurl = st.text_area("If capture didn't auto-load, paste dataURL from page here")
    if dataurl:
        try:
            header, encoded = dataurl.split(",", 1)
            uploaded = io.BytesIO(base64.b64decode(encoded))
        except:
            st.error("Invalid dataURL")

# -----------------------
# Generate & download
# -----------------------
st.header("3) Generate stamped image")
if st.button("Generate"):
    if not uploaded:
        st.error("Please upload or capture an image first.")
    elif lat is None or lon is None:
        st.error("Please provide coordinates (paste or use detected coords).")
    else:
        # Open image
        try:
            img = Image.open(uploaded).convert("RGB")
        except Exception as e:
            st.error(f"Could not open image: {e}")
            st.stop()

        # Reverse geocode (Nominatim)
        address = ""
        try:
            r = requests.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"format": "jsonv2", "lat": lat, "lon": lon},
                headers={"User-Agent": "Simple-GPS-Map-Camera/1.0"},
                timeout=8,
            )
            address = r.json().get("display_name", "")
        except:
            address = ""

        # Fetch small static OSM map
        map_img = None
        try:
            map_url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=16&size=160x160&markers={lat},{lon},red-pushpin"
            rr = requests.get(map_url, timeout=8)
            map_img = Image.open(io.BytesIO(rr.content)).convert("RGBA")
        except:
            map_img = None

        # Prepare drawing
        W, H = img.size
        out = img.convert("RGBA")
        draw = ImageDraw.Draw(out)

        # Fonts (fallback to default)
        try:
            font_big = ImageFont.truetype("DejaVuSans-Bold.ttf", max(20, W//30))
            font_small = ImageFont.truetype("DejaVuSans.ttf", max(14, W//55))
        except:
            font_big = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # Compose texts
        now = datetime.datetime.now().strftime("%d/%m/%Y %I:%M %p")
        title = address if address else f"Lat {lat:.6f}, Lon {lon:.6f}"
        subtitle = f"Lat {lat:.6f}  Lon {lon:.6f}\n{now}"

        # Draw translucent box at bottom
        box_h = int(H * 0.22)
        overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle([0, H - box_h, W, H], fill=(0, 0, 0, 180))
        out = Image.alpha_composite(out, overlay)
        draw = ImageDraw.Draw(out)

        # Draw title
        padding = 18
        draw.text((padding, H - box_h + padding), title, font=font_big, fill=(255, 255, 255, 255))
        # Draw subtitle (two lines)
        y_sub = H - box_h + padding + (font_big.getsize(title)[1] + 8)
        for i, line in enumerate(subtitle.split("\n")):
            draw.text((padding, y_sub + i * (font_small.getsize(line)[1] + 4)), line, font=font_small, fill=(230, 230, 230, 255))

        # Paste map inset bottom-left (overlapping box) if available
        if map_img:
            thumb_w, thumb_h = map_img.size
            border = 4
            bg = Image.new("RGBA", (thumb_w + border*2, thumb_h + border*2), (255, 255, 255, 255))
            bg.paste(map_img, (border, border), map_img)
            map_x = 12
            map_y = H - box_h - thumb_h//2
            out.paste(bg, (map_x, map_y), bg)

        final = out.convert("RGB")

        # Output & download link
        st.image(final, caption="Stamped image", use_column_width=True)
        buf = io.BytesIO()
        final.save(buf, format="JPEG", quality=92)
        b64 = base64.b64encode(buf.getvalue()).decode()
        st.markdown(f'<a href="data:file/jpg;base64,{b64}" download="stamped.jpg">⬇️ Download stamped image</a>', unsafe_allow_html=True)
