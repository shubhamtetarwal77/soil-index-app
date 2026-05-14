# ==========================================================
# Soil Index  - OPTION A (FASTEST STABLE)
# FULL MASTER VERSION
# Fixes:
# ✔ no snap back
# ✔ no double drag
# ✔ no double zoom
# ✔ no OSM auto switching
# ✔ smooth map movement
# ✔ spatial layer stable
# ✔ keeps all original features
# ==========================================================
import streamlit as st
import ee
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import io
import zipfile
from streamlit_folium import st_folium
import folium
from folium.plugins import (
    Draw,
    Fullscreen,
    MousePosition,
    MeasureControl
)
import json
import os
# ==========================================================
# PAGE
# ==========================================================
st.set_page_config(
    layout="wide",
    page_title="Soil Index "
)
# ==========================================================
# AUTH (The Clean-Key Version)
# ==========================================================
if "ee_initialized" not in st.session_state:
    try:
        if "gee_key" in st.secrets:
            # WEB MODE
            s = st.secrets["gee_key"]
            
            # This line fixes the PEM formatting error by ensuring newlines are real
            clean_key = s["private_key"].replace("\\n", "\n")
            
            credentials = ee.ServiceAccountCredentials(
                s["client_email"],
                key_data=clean_key
            )
            ee.Initialize(credentials, project=s["project_id"])
        else:
            # LOCAL MODE
            service_account = "soil-index@field-analytics-493911.iam.gserviceaccount.com"
            json_key = "field-analytics-493911-38f78a41b0d6.json"
            credentials = ee.ServiceAccountCredentials(service_account, json_key)
            ee.Initialize(credentials, project="field-analytics-493911")
            
        st.session_state.ee_initialized = True
    except Exception as e:
        st.error(f"Earth Engine Error: {e}")
# ==========================================================
# SESSION STATES
# ==========================================================
defaults = {
    "map_center": [20.5937, 78.9629],
    "map_zoom": 4,
    "map_key": 0,
    "show_layer": False,
    "map_data": None,
    "current_field_data": {},
    "individual_rois": [],
    "last_roi": None,
    "active_basemap": "Satellite",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
# ===== RENAME MODE STATE =====
if "rename_mode" not in st.session_state:
    st.session_state.rename_mode = False
# ===== SAVED FIELDS STORAGE =====
FILE_PATH = os.path.join(os.getcwd(), "saved_fields.json")
if "saved_fields" not in st.session_state:
    if os.path.exists(FILE_PATH):
        with open(FILE_PATH, "r") as f:
            st.session_state.saved_fields = json.load(f)
    else:
        st.session_state.saved_fields = {}
# ==========================================================
# INDEX CONFIG
# ==========================================================
INDEX_REGISTRY = {
    "NDVI": {"bands": ["B8", "B4"], "min": -1, "max": 1},
    "NDMI": {"bands": ["B8", "B11"], "min": -0.8, "max": 0.8},
    "NDRE": {"bands": ["B8", "B5"], "min": -1, "max": 1},
    "GCI": {"bands": None, "min": 0, "max": 5},
    "MSAVI": {"bands": None, "min": -1, "max": 1},
    "EVI": {"bands": None, "min": -1, "max": 1},
    "SAVI": {"bands": None, "min": -1, "max": 1},
    "NDWI": {"bands": ["B3", "B8"], "min": -1, "max": 1},
    "CCCI": {"bands": None, "min": 0, "max": 1},
}
# ==========================================================
# INDEX-SPECIFIC THRESHOLDS
# ==========================================================
INDEX_THRESHOLDS = {
    "NDVI": {
        "poor": 0.35,
        "moderate": 0.6
    },
    "NDMI": {
        "poor": 0.15,
        "moderate": 0.35
    },
    "NDRE": {
        "poor": 0.35,
        "moderate": 0.6
    },
    "GCI": {
        "poor": 1.5,
        "moderate": 3.5
    },
    "MSAVI": {
        "poor": 0.35,
        "moderate": 0.6
    },
    "EVI": {
        "poor": 0.35,
        "moderate": 0.6
    },
    "SAVI": {
        "poor": 0.25,
        "moderate": 0.55
    },
    "NDWI": {
        "poor": -0.1,
        "moderate": 0.2
    },
    "CCCI": {
        "poor": 0.4,
        "moderate": 0.8
    }
}
# ==========================================================
# INDEX FUNCTION
# ==========================================================
# HEALTH CLASSIFICATION
# ==========================================================
def classify_index(val, index_type):
    if val is None:
        return "No Data"
    th = INDEX_THRESHOLDS[index_type]
    if val < th["poor"]:
        return "🔴 Poor"
    elif val < th["moderate"]:
        return "🟡 Moderate"
    else:
        return "🟢 Healthy"
def get_index_image_from_img(s2, index_type):
    cfg = INDEX_REGISTRY[index_type]
    if cfg["bands"]:
        return s2.normalizedDifference(cfg["bands"]).rename("v")
    if index_type == "GCI":
        return s2.select("B8").divide(
            s2.select("B3")
        ).subtract(1).rename("v")
    if index_type == "MSAVI":
        nir = s2.select("B8")
        red = s2.select("B4")
        return (
            nir.multiply(2)
            .add(1)
            .subtract(
                nir.multiply(2)
                .add(1)
                .pow(2)
                .subtract(
                    nir.subtract(red).multiply(8)
                )
                .sqrt()
            )
            .divide(2)
            .rename("v")
        )
    if index_type == "EVI":
        nir = s2.select("B8")
        red = s2.select("B4")
        blue = s2.select("B2")
        return (
            nir.subtract(red)
            .multiply(2.5)
            .divide(
                nir.add(red.multiply(6))
                .subtract(blue.multiply(7.5))
                .add(1)
            )
            .rename("v")
        )
    if index_type == "SAVI":
        nir = s2.select("B8")
        red = s2.select("B4")
        L = 0.5
        return (
            nir.subtract(red)
            .divide(nir.add(red).add(L))
            .multiply(1 + L)
            .rename("v")
        )
    if index_type == "NDWI":
        return s2.normalizedDifference(["B3", "B8"]).rename("v")
    if index_type == "CCCI":
        nir = s2.select("B8")
        red = s2.select("B4")
        red_edge = s2.select("B5")
        ndvi = nir.subtract(red).divide(nir.add(red))
        ndre = nir.subtract(red_edge).divide(nir.add(red_edge))
        return ndre.divide(ndvi).rename("v")
    return s2.select([0]).multiply(0).rename("v")
# ==========================================================
# SIDEBAR
# ==========================================================
with st.sidebar:
    st.header("Controls")
    index_dropdown = st.selectbox(
        "Select Index",
        list(INDEX_REGISTRY.keys())
    )
    date_picker = st.date_input(
        "Map Date",
        value=datetime(2025, 8, 11)
    )
    trend_start = st.date_input(
        "Trend Start",
        value=datetime(2025, 1, 1)
    )
    trend_end = st.date_input(
        "Trend End",
        value=datetime(2025, 8, 11)
    )
    st.divider()
    # ✅ ADD THIS LINE
    btn_spatial = st.button("Generate Spatial Layer", type="primary")
    # ✅ PASTE HERE
    st.subheader("📂 Saved Fields")
    field_names = list(st.session_state.saved_fields.keys())
    col1, col2, col3 = st.columns([6, 1, 1])
    with col1:
        selected_fields = st.multiselect(
            "Select Field",
            field_names
        )
        # Handle single selection for rename/delete
    selected_field = selected_fields[0] if len(selected_fields) == 1 else None
    with col2:
        delete_clicked = st.button("🗑", help="Delete Field")
    with col3:
        if st.button("✏️", help="Rename Field"):
            st.session_state.rename_mode = True
    # ===== DELETE =====
    if selected_field and delete_clicked:
        if selected_field in st.session_state.saved_fields:
            del st.session_state.saved_fields[selected_field]
            with open(FILE_PATH, "w") as f:
                json.dump(st.session_state.saved_fields, f, indent=2)
            # ✅ CLEAR STALE STATE (IMPORTANT)
            st.session_state.individual_rois = []
            st.session_state.last_roi = None
            st.success(f"{selected_field} deleted ✅")
            st.rerun()
        # RESET SPATIAL STATE IF NOTHING LEFT
        if not st.session_state.saved_fields:
            st.session_state.last_roi = None
            st.session_state.individual_rois = []
            st.session_state.show_layer = False
            st.session_state.map_key += 1
            st.rerun()
    # ===== RENAME =====
    # ===== RENAME MODE UI =====
    if selected_field and st.session_state.rename_mode:
        new_name = st.text_input("Enter New Name")
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            if st.button("✅ Save"):
                if not new_name:
                    st.warning("Enter new name")
                elif new_name in st.session_state.saved_fields:
                    st.warning("Name already exists")
                else:
                    st.session_state.saved_fields[new_name] = \
                        st.session_state.saved_fields.pop(selected_field)
                    with open(FILE_PATH, "w") as f:
                        json.dump(st.session_state.saved_fields, f, indent=2)
                    st.success(f"Renamed to {new_name} ✅")
                    st.session_state.rename_mode = False
                    st.rerun()
        with col_r2:
            if st.button("❌ Cancel"):
                st.session_state.rename_mode = False
                st.rerun()
    # ===== LOAD FIELD =====
    if selected_fields:
        rois = []
        for fname in selected_fields:
            if fname not in st.session_state.saved_fields:
                continue  # ✅ prevents KeyError
            field = st.session_state.saved_fields[fname]
            geom = ee.Geometry(field["geometry"])
            rois.append(geom)
        # Store all selected ROIs
        st.session_state.individual_rois = rois
        st.session_state.last_roi = ee.FeatureCollection(rois).geometry()
        st.session_state.show_layer = True
        # Center map on first field
        coords = rois[0].bounds().coordinates().getInfo()
        lons = [c[0] for c in coords[0]]
        lats = [c[1] for c in coords[0]]
        st.session_state.map_center = [
            sum(lats)/len(lats),
            sum(lons)/len(lons)
        ]
        st.session_state.map_zoom = 17
        # Show info
        for fname in selected_fields:
            st.write(f"📍 {fname}")
        st.divider()
    st.subheader("Search")
    search_point = st.text_input(
        "Go To Lat,Lon",
        placeholder="26.774,76.013"
    )
    if st.button("Go To Point"):
        try:
            lat, lon = map(float, search_point.split(","))
            st.session_state.map_center = [lat, lon]
            # fly zoom style
            st.session_state.map_zoom = 18
            st.session_state.map_key += 1
            st.rerun()
        except:
            st.warning("Use lat,lon")
    polygon_text = st.text_area(
        "Polygon Coordinates (lon,lat)",
        placeholder="""76.013,26.774
76.014,26.774
76.014,26.775
76.013,26.775
76.013,26.774"""
    )
    if st.button("Add Polygon"):
        try:
            coords = []
            for line in polygon_text.strip().split("\n"):
                lon, lat = map(float, line.split(","))
                coords.append([lon, lat])
            poly = ee.Geometry.Polygon([coords])
            st.session_state.individual_rois = [poly]
            st.session_state.last_roi = poly
            st.session_state.map_center = [
                coords[0][1],
                coords[0][0]
            ]
            st.session_state.map_zoom = 17
            st.session_state.map_key += 1
            st.success("Polygon Loaded")
            st.rerun()
        except:
            st.warning("Invalid Polygon")
# ==========================================================
# TITLE
# ==========================================================
st.title("🌿 Soil Index ")
# ==========================================================
# LIVE MAP MEMORY
# ==========================================================
center = st.session_state.map_center
zoom = st.session_state.map_zoom
# ==========================================================
# MAP
# ==========================================================
m = folium.Map(
    location=center,
    zoom_start=zoom,
    control_scale=True,
    prefer_canvas=True,
    zoom_control=True
)
# ==========================================================
# SAFETY CLEANUP (CRITICAL)
# ==========================================================
if not st.session_state.saved_fields:
    st.session_state.last_roi = None
    st.session_state.individual_rois = []
    st.session_state.show_layer = False
# ---------- SATELLITE ----------
folium.TileLayer(
    tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    attr="Google",
    name="Satellite",
    overlay=False,
    control=True,
    show=True
).add_to(m)
# ---------- HYBRID ----------
folium.TileLayer(
    tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
    attr="Google",
    name="Hybrid",
    overlay=False,
    control=True,
    show=False
).add_to(m)
# ==========================================================
# INDEX OVERLAY
# ==========================================================
# ===== ROI BORDER (SAFE + SYNCED) =====
if st.session_state.last_roi is not None:
    try:
        folium.GeoJson(
            data=st.session_state.last_roi.getInfo(),
            name="Field Boundary",
            style_function=lambda x: {
                "color": "blue",
                "weight": 2,
                "fillOpacity": 0
            }
        ).add_to(m)
    except:
        pass
    roi = st.session_state.last_roi
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(roi)
        .filterDate(
            date_picker.strftime("%Y-%m-%d"),
            datetime.now().strftime("%Y-%m-%d")
        )
        .filter(ee.Filter.lt(
            "CLOUDY_PIXEL_PERCENTAGE",
            30
        ))
    )
    img = col.median()
    overlay = get_index_image_from_img(
        img,
        index_dropdown
    )
    vis = INDEX_REGISTRY[index_dropdown]
    th = INDEX_THRESHOLDS[index_dropdown]
    min_val = vis["min"]
    p = th["poor"]
    moderate_val = th["moderate"]
    max_val = vis["max"]
    th = INDEX_THRESHOLDS[index_dropdown]
    # 🎨 Dynamic palette based on index
    if index_dropdown in ["NDWI", "NDMI"]:
        palette = [
            "#f7fbff",  # very low (dry)
            "#c6dbef",
            "#6baed6",
            "#2171b5",
            "#08306b"   # high water
        ]
    else:
        palette = [
            "#8B0000", "#FF0000",
            "#FFA500", "#FFFF00",
            "#ADFF2F", "#008000"
        ]
    mp = overlay.clip(roi).getMapId({
        "min": vis["min"],
        "max": vis["max"],
        "palette": palette
    })
    folium.TileLayer(
        tiles=mp["tile_fetcher"].url_format,
        attr="GEE",
        name=f"{index_dropdown} Overlay",
        overlay=True,
        control=True
    ).add_to(m)
# ==========================================================
# TOOLS
# ==========================================================
Fullscreen().add_to(m)
MeasureControl(
    primary_length_unit="meters"
).add_to(m)
MousePosition(
    position="bottomright",
    prefix="Lat/Lon"
).add_to(m)
Draw(
    export=False,
    draw_options={
        "polyline": False,
        "circle": False,
        "marker": False,
        "circlemarker": False,
        "polygon": True,
        "rectangle": True
    },
    edit_options={
        "edit": True,
        "remove": True
    }
).add_to(m)
# Always visible layer control
folium.LayerControl(
    position="topright",
    collapsed=False
).add_to(m)
# ==========================================================
# LEGEND (VERTICAL + TICKS)
# ==========================================================
vis = INDEX_REGISTRY[index_dropdown]
min_val = vis["min"]
max_val = vis["max"]
mid_val = (min_val + max_val) / 2
custom_css = """
<style>
.map-overlay {
    position: fixed;   /* 🔥 CHANGE from absolute → fixed */
    z-index: 9999;
    background: rgba(30, 41, 59, 0.75);
    color: white;
    backdrop-filter: blur(6px);
    border: 1px solid rgba(0,0,0,0.2);
    padding: 10px;
    border-radius: 8px;
    font-size: 12px;
}
.legend-box {
    top: 140px;
    right: 30px;
}
.zone-box {
    bottom: 40px;
    right: 30px;
}
</style>
"""
m.get_root().header.add_child(folium.Element(custom_css))
# 🎨 Dynamic legend gradient
if index_dropdown in ["NDWI", "NDMI"]:
    gradient = "linear-gradient(to top, #f7fbff, #c6dbef, #6baed6, #2171b5, #08306b)"
else:
    gradient = "linear-gradient(to top, #8B0000, #FF0000, #FFA500, #FFFF00, #ADFF2F, #008000)"
legend_html = f"""
<div class="map-overlay legend-box">
<b>{index_dropdown}</b><br><br>
<div style="display:flex; align-items:center; justify-content:center;">
    <div style="position: relative; height:150px; margin-right:8px;">
        <div style="position:absolute; top:0;">
            <span>{max_val:.2f}</span>
        </div>
        <div style="position:absolute; top:50%; transform: translateY(-50%);">
            <span>{mid_val:.2f}</span>
        </div>
        <div style="position:absolute; bottom:0;">
            <span>{min_val:.2f}</span>
        </div>
    </div>
    <div style="
    height:150px;
    width:15px;
    background: {gradient};
    border-radius: 4px;">
    </div>
</div>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))
# FLOATING ZONE SUMMARY PANEL (LIKE LEGEND)
# ==========================================================
# ==========================================================
# DISPLAY MAP (FINAL NO RENDER VERSION)
# ==========================================================
if st.session_state.last_roi is not None:
    roi = st.session_state.last_roi
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(roi)
        .filterDate(
            date_picker.strftime("%Y-%m-%d"),
            datetime.now().strftime("%Y-%m-%d")
        )
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
    )
    img = col.median()
    index_img = get_index_image_from_img(img, index_dropdown)
    stats = index_img.reduceRegion(
        reducer=ee.Reducer.minMax()
            .combine(ee.Reducer.mean(), '', True)
            .combine(ee.Reducer.stdDev(), '', True),
        geometry=roi,
        scale=10,
        bestEffort=True
    ).getInfo()
    if stats:
        min_val = stats.get("v_min")
        max_val = stats.get("v_max")
        mean_val = stats.get("v_mean")
        std_val = stats.get("v_stdDev")
        # ===== SAMPLE FOR DISTRIBUTION =====
        samples = index_img.sample(
            region=roi,
            scale=10,
            numPixels=500
        ).getInfo()["features"]
        counts = {"Poor": 0, "Moderate": 0, "Healthy": 0}
        for f in samples:
            v = f["properties"]["v"]
            if v is not None:
                th = INDEX_THRESHOLDS[index_dropdown]
                if v < th["poor"]:
                    counts["Poor"] += 1
                elif v < th["moderate"]:
                    counts["Moderate"] += 1
                else:
                    counts["Healthy"] += 1
        total = sum(counts.values())
        if total > 0:
            poor_pct = (counts["Poor"] / total) * 100
            mod_pct = (counts["Moderate"] / total) * 100
            good_pct = (counts["Healthy"] / total) * 100
            zone_html = f"""
            <div class="map-overlay zone-box">
            <b>📊 Zone Summary</b><br><br>
            <b>Min:</b> {min_val:.3f}<br>
            <b>Max:</b> {max_val:.3f}<br>
            <b>Mean:</b> {mean_val:.3f}<br>
            <b>Std:</b> {std_val:.3f}<br><br>
            🔴 Poor: {poor_pct:.1f}%<br>
            🟡 Moderate: {mod_pct:.1f}%<br>
            🟢 Healthy: {good_pct:.1f}%
            </div>
            """
            m.get_root().html.add_child(folium.Element(zone_html))
map_data = st_folium(
    m,
    height=680,
    width=None,
    key=f"main_map_{st.session_state.map_key}",
    returned_objects=[
        "all_drawings",
        "last_clicked"
    ]
)
st.session_state.map_data = map_data
# Save current position silently (NO rerun)
if map_data:
    if map_data.get("center"):
        st.session_state.map_center = [
            map_data["center"]["lat"],
            map_data["center"]["lng"]
        ]
    if map_data.get("zoom"):
        st.session_state.map_zoom = map_data["zoom"]
# ==========================================================
# GENERATE SPATIAL (FIXED FOR ALL MODES)
# ==========================================================
if btn_spatial:
    with st.spinner("Processing satellite data..."):
        rois = []
        # CASE 1: Drawn polygons from map
        latest_map = st.session_state.map_data
        if latest_map and latest_map.get("all_drawings"):
            rois = [
                ee.Geometry(d["geometry"])
                for d in latest_map["all_drawings"]
            ]
        # CASE 2: Saved fields selection
        elif selected_fields:
            for fname in selected_fields:
                field = st.session_state.saved_fields[fname]
                rois.append(ee.Geometry(field["geometry"]))
        # CASE 3: fallback (already stored ROIs)
        elif st.session_state.individual_rois:
            rois = st.session_state.individual_rois
        else:
            st.warning("No field or polygon selected")
            st.stop()
        # SAVE ROIS
        st.session_state.individual_rois = rois
        st.session_state.last_roi = ee.FeatureCollection(rois).geometry()
        st.session_state.show_layer = True
        # CENTER MAP
        coords = rois[0].bounds().coordinates().getInfo()
        lons = [c[0] for c in coords[0]]
        lats = [c[1] for c in coords[0]]
        st.session_state.map_center = [
            sum(lats) / len(lats),
            sum(lons) / len(lons)
        ]
        st.session_state.map_zoom = 17
        st.session_state.map_key += 1
        st.success("Spatial Layer Generated")
        st.rerun()
# ==========================================================
# AREA PANEL (FIXED FOR MULTI-FIELDS + DRAWINGS)
# ==========================================================
st.subheader("Field Area")
# CASE 1: DRAWN POLYGONS
if map_data and map_data.get("all_drawings"):
    for i, d in enumerate(map_data["all_drawings"], start=1):
        g = ee.Geometry(d["geometry"])
        sqm = g.area().getInfo()
        acre = sqm / 4046.85642
        ha = sqm / 10000
        st.write(
            f"Drawn Field {i}: "
            f"{acre:.2f} Acre | "
            f"{ha:.2f} Hectare"
        )
# CASE 2: SAVED MULTI-FIELDS (THIS IS YOUR BUG FIX)
elif st.session_state.individual_rois:
    for i, geom in enumerate(st.session_state.individual_rois, start=1):
        sqm = ee.Geometry(geom).area().getInfo()
        acre = sqm / 4046.85642
        ha = sqm / 10000
        st.write(
            f"Saved Field {i}: "
            f"{acre:.2f} Acre | "
            f"{ha:.2f} Hectare"
        )
# ==========================================================
# SAVE FIELD
# ==========================================================
if map_data and map_data.get("all_drawings"):
    drawings = map_data["all_drawings"]
    st.subheader("💾 Save Field")
    field_name = st.text_input("Enter Field Name")
    if st.button("Save This Field"):
        if not field_name:
            st.warning("Enter a name")
        else:
            geom = ee.Geometry(drawings[-1]["geometry"])
            area = geom.area().getInfo()
            acre = area / 4046.85642
            ha = area / 10000
            st.session_state.saved_fields[field_name] = {
                "geometry": drawings[-1]["geometry"],
                "area_acre": round(acre, 2),
                "area_ha": round(ha, 2)
            }
            with open(FILE_PATH, "w") as f:
                json.dump(st.session_state.saved_fields, f, indent=2)
            st.success(f"Field '{field_name}' saved ✅")
# ==========================================================
# INSPECTOR CLICK
# ==========================================================
if map_data and map_data.get("last_clicked"):
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]
    pt = ee.Geometry.Point([lon, lat])
    st.subheader("Inspector")
    st.write(f"Location: {lat:.5f}, {lon:.5f}")
    s2 = (
        ee.ImageCollection(
            "COPERNICUS/S2_SR_HARMONIZED"
        )
        .filterBounds(pt)
        .filterDate(
            date_picker.strftime("%Y-%m-%d"),
            datetime.now().strftime("%Y-%m-%d")
        )
        .sort("system:time_start", False)
        .first()
    )
    if s2:
        img = get_index_image_from_img(
            s2,
            index_dropdown
        )
        val = img.sample(
            pt,
            10
        ).first().get("v").getInfo()
        if val is not None:
            st.metric(
                f"{index_dropdown}",
                f"{val:.4f}"
            )
            st.write("Health:", classify_index(val, index_dropdown))
            # ===== SMART ADVICE =====
            if index_dropdown == "NDVI":
                if val < 0.3:
                    st.error("Crop condition is poor. Check irrigation & nutrients.")
                elif val < 0.6:
                    st.warning("Moderate growth. Monitor fertilizer usage.")
                else:
                    st.success("Healthy crop. Maintain current practices.")
# TREND FUNCTION (ALL MODES SINGLE GRAPH)
# ==========================================================
def run_hybrid_trend(mode, is_weather=False):
    features = map_data.get("all_drawings") if map_data else None
    if not features:
        features = st.session_state.individual_rois
    if not features:
        st.warning("No Fields Found")
        return
    st.session_state.current_field_data = {}
    start_dt = trend_start.strftime("%Y-%m-%d")
    end_dt = trend_end.strftime("%Y-%m-%d")
    # Single graph for all fields
    fig, ax = plt.subplots(figsize=(14, 6))
    for i, feat in enumerate(features):
        roi = (
            ee.Geometry(feat["geometry"])
            if isinstance(feat, dict)
            else feat
        )
        field = f"Field_{i+1}"
        # ==================================================
        # INDEX MODE
        # ==================================================
        if not is_weather:
            col = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(roi)
                .filterDate(start_dt, end_dt)
                .filter(
                    ee.Filter.lt(
                        "CLOUDY_PIXEL_PERCENTAGE", 30
                    )
                )
            )
            stats = col.map(
                lambda img: ee.Feature(None, {
                    "v": get_index_image_from_img(
                        img, mode
                    ).reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=roi,
                        scale=10,
                        bestEffort=True
                    ).get("v"),
                    "t": img.get("system:time_start")
                })
            ).getInfo()["features"]
        # ==================================================
        # WEATHER MODE
        # ==================================================
        else:
            dataset = "ECMWF/ERA5_LAND/DAILY_AGGR"
            band = (
                "temperature_2m"
                if mode == "Temp"
                else "total_precipitation_sum"
            )
            col = (
                ee.ImageCollection(dataset)
                .filterBounds(roi)
                .filterDate(start_dt, end_dt)
            )
            stats = col.map(
                lambda img: ee.Feature(None, {
                    "v": img.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=roi,
                        scale=1000,
                        bestEffort=True,
                        maxPixels=1e13
                    ).get(band),
                    "t": img.get("system:time_start")
                })
            ).getInfo()["features"]
        # ==================================================
        # DATA PROCESS
        # ==================================================
        dates = []
        values = []
        for f in stats:
            p = f.get("properties", {})
            if "v" in p and p["v"] is not None:
                dates.append(
                    datetime.fromtimestamp(
                        p["t"] / 1000
                    )
                )
                val = p["v"]
                if mode == "Temp":
                    val = val - 273.15
                if mode == "Rain":
                    val = val * 1000
                values.append(val)
        # ===== WEATHER ALERT (FIXED) =====
        if is_weather and values:
            avg_temp = sum(values) / len(values)
            if mode == "Temp":
                if avg_temp > 35:
                    st.warning("🔥 High temperature stress risk")
                elif avg_temp < 10:
                    st.warning("❄️ Cold stress risk")
        # ==================================================
        # STORE CSV
        # ==================================================
        if len(dates) > 0:
            df = pd.DataFrame({
                "Date": dates,
                mode: values
            })
            st.session_state.current_field_data[field] = df
            # Plot on same graph
            ax.plot(
                dates,
                values,
                marker="o",
                linewidth=2,
                label=field
            )
    # ==================================================
    # FINAL GRAPH
    # ==================================================
    ax.set_title(f"{mode} Trend Comparison", fontsize=18)
    ax.legend()
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)
    # ===== DOWNLOAD GRAPH =====
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    buf.seek(0)
    st.download_button(
        "Download Graph",
        data=buf.getvalue(),
        file_name=f"{mode}_trend.png"
    )
# ==================================================
# SUMMARY TABLE
# ==================================================
summary = []
for name, df in st.session_state.current_field_data.items():
    summary.append({
        "Field": name,
        "Mean": round(df.iloc[:,1].mean(), 3),
        "Max": round(df.iloc[:,1].max(), 3),
        "Min": round(df.iloc[:,1].min(), 3)
    })
st.subheader("Field Comparison Summary")
st.dataframe(pd.DataFrame(summary))
# ==========================================================
# BUTTONS
# ==========================================================
st.write("### Analysis")
c1, c2, c3, c4 = st.columns(4)
if c1.button("Index Trend"):
    run_hybrid_trend(index_dropdown, False)
if c2.button("Temp Trend"):
    run_hybrid_trend("Temp", True)
if c3.button("Rain Trend"):
    run_hybrid_trend("Rain", True)
if c4.button("Export CSV"):
    if not st.session_state.current_field_data:
        st.warning("Run Trend First")
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(
            zip_buffer,
            "a",
            zipfile.ZIP_DEFLATED,
            False
        ) as z:
            for name, df in st.session_state.current_field_data.items():
                z.writestr(
                    f"{name}.csv",
                    df.to_csv(index=False)
                )
        st.download_button(
            "Download ZIP",
            data=zip_buffer.getvalue(),
            file_name="Field_Reports.zip"
        )
