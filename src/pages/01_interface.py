import leafmap
import solara
from urllib.parse import quote
from localtileserver import TileClient
import os
from pathlib import Path
import pandas as pd
import geopandas as gpd
from shapely import Polygon
import rioxarray as rxr
import ipywidgets as widgets
import requests
from urllib.parse import quote
import math


data_dir = Path('/home/jovyan/solara-labeler/src/public/')
years = [2019, 2021, 2023]

# Display Styles
styledict = {
            "stroke": True,
            "color": "#FF0000",
            "weight": 3,
            "opacity": 1,
            "fill": False,
        }
hover_style_dict = {
    "weight": styledict["weight"],
    "fillOpacity": 0,
    "color": styledict["color"],
}

zoom = solara.reactive(20)
center = solara.reactive((42.251504, -71.823585))
current_chip = solara.reactive(None)
previous_chip = solara.reactive(None)

def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    return (xtile, ytile)

def bbox_to_tiles(bbox, zoom):
    # bbox = (min_lon, min_lat, max_lon, max_lat)
    min_x, max_y = deg2num(bbox[1], bbox[0], zoom)  # north-west corner
    max_x, min_y = deg2num(bbox[3], bbox[2], zoom)  # south-east corner
    tiles = []
    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            tiles.append((zoom, x, y))
    return tiles
    
def display_chip(m, styledict, hover_style_dict):
    """Display a chip on the map"""
    #chip_id.set(chip_gdf.iloc[0]['id'])
    chip_gdf = current_chip.value
    c = [c[0] for c in chip_gdf.to_crs('EPSG:4326').iloc[0].geometry.centroid.coords.xy]
    
    # Remove existing chip layer
    for layer in list(m.layers):
        if layer.name == 'chip':
            m.remove_layer(layer)
    
    # Add new chip to map
    m.add_gdf(
        chip_gdf,
        zoom_to_layer=False,
        style=styledict,
        hover_style=hover_style_dict,
        layer_name='chip',
        info_mode=None
    )
    
    center.set((c[1], c[0]))
    zoom.set(20)
    setattr(m, "gdf", chip_gdf)

def add_widgets(m, data_dir, styledict, hover_style_dict):

    def get_previous_chip(b):
        current_chip.set(previous_chip.value)
        display_chip(m, styledict, hover_style_dict)

    def next_chip(b):
        # save the previous chip for re-doing
        if current_chip.value is not None:
            previous_chip.set(current_chip.value)

        # read in chip tracker
        chips = pd.read_csv(data_dir / 'chip_tracker.csv')
        
        # get all chips with pending status
        labeled_chips = chips[chips['status'] == 'pending']

        # get the first chip
        new_chip = labeled_chips.head(1).copy()

        # mark this chip as active and save to tracker on disk
        chips.loc[new_chip.index, 'status'] = 'active'
        chips.to_csv(data_dir / 'chip_tracker.csv', index=False)
        
        # re-constitute the geometry
        new_chip['geometry'] = new_chip['bbox'].apply(lambda coord_str: Polygon(eval(coord_str)))
        
        # set the current chip equal to the new chip gdf
        chip_gdf = gpd.GeoDataFrame(new_chip, geometry='geometry', crs='EPSG:6348').to_crs('EPSG:3857')
        current_chip.set(chip_gdf)

        # display the chip on the map
        display_chip(m, styledict, hover_style_dict)

    def clear_rois(b):
        m.draw_control.clear()
       
    def save_rois(b):
        # Get the current chip information
        if current_chip.value is None:
            print("No active chip to save ROIs for")
            return
        
        chip_id = current_chip.value.iloc[0]['id']
        
        # Get all drawn features from the map
        drawn_features = m.user_rois
        
        if not drawn_features:
            print("No ROIs drawn on the map")
            return
        
        # Create a GeoDataFrame from the drawn features
        features = []
        for feature in drawn_features['features']:
            geom = feature['geometry']
            feat_type = geom['type']
            
            # Convert to shapely geometry
            if feat_type == 'Polygon':
                coords = geom['coordinates'][0]  # First ring is exterior
                features.append({
                    'chip_id': chip_id,
                    'geometry': Polygon(coords),
                    'timestamp': pd.Timestamp.now().isoformat(),
                })
        
        if features:
            # Create GeoDataFrame and save to file
            rois_gdf = gpd.GeoDataFrame(features, geometry='geometry', crs='EPSG:3857')
            
            # Convert to appropriate CRS if needed
            rois_gdf = rois_gdf.to_crs('EPSG:6348')
            
            # Save to file
            output_path = data_dir / 'outputs' / f'{chip_id}_labels.geojson'
            
            rois_gdf.to_file(output_path, driver='GeoJSON')
            
            print(f"Saved {len(features)} ROIs to {output_path}")

    def mark_chip_labeled(b):
        chip_id = current_chip.value.iloc[0]['id']
        # Update chip status to labeled in tracker
        chips = pd.read_csv(data_dir / 'chip_tracker.csv')
        chip_idx = chips[chips['id'] == chip_id].index
        if len(chip_idx) > 0:
            chips.loc[chip_idx, 'status'] = 'labeled'
            chips.to_csv(data_dir / 'chip_tracker.csv', index=False) 

    def mark_chip_active(b):
        chip_id = current_chip.value.iloc[0]['id']
        # Update chip status to labeled in tracker
        chips = pd.read_csv(data_dir / 'chip_tracker.csv')
        chip_idx = chips[chips['id'] == chip_id].index
        if len(chip_idx) > 0:
            chips.loc[chip_idx, 'status'] = 'active'
            chips.to_csv(data_dir / 'chip_tracker.csv', index=False) 

    def mark_chip_pending(b):
        chip_id = current_chip.value.iloc[0]['id']
        # Update chip status to labeled in tracker
        chips = pd.read_csv(data_dir / 'chip_tracker.csv')
        chip_idx = chips[chips['id'] == chip_id].index
        if len(chip_idx) > 0:
            chips.loc[chip_idx, 'status'] = 'pending'
            chips.to_csv(data_dir / 'chip_tracker.csv', index=False) 

    def remove_rois(b):
        # Remove rois for the current chip
        # Get the current chip information
        if current_chip.value is None:
            print("No active chip to delete ROIs for")
            return
        chip_id = current_chip.value.iloc[0]['id']

        output_path = data_dir / 'outputs' / f'{chip_id}_labels.geojson'
        output_path.unlink()
        
        # Update chip status to labeled in tracker
        chips = pd.read_csv(data_dir / 'chip_tracker.csv')
        chip_idx = chips[chips['id'] == chip_id].index
        if len(chip_idx) > 0:
            chips.loc[chip_idx, 'status'] = 'active'
            chips.to_csv(data_dir / 'chip_tracker.csv', index=False)

    def back_to_last_chip(b):
        mark_chip_pending(b)
        clear_rois(b)
        get_previous_chip(b)
        remove_rois(b)
        mark_chip_active(b)

    def submit_chip(b):
        save_rois(b)
        mark_chip_labeled(b)
        clear_rois(b)
        next_chip(b)

        
    back_to_last_chip_button = widgets.Button(description="Go back and redo last chip")
    
    submit_chip_button = widgets.Button(description="Save Labels to Disk", 
                            button_style='success',
                            tooltip='Save drawn regions to file')
    
    delete_labels_button = widgets.Button(description="Delete Labels for current chip from Disk")
    

    back_to_last_chip_button.on_click(back_to_last_chip)
    submit_chip_button.on_click(submit_chip)
    delete_labels_button.on_click(remove_rois)

    m.add_widget(back_to_last_chip_button)
    m.add_widget(submit_chip_button)
    m.add_widget(delete_labels_button)

    next_chip(None)

class LabelMap(leafmap.Map):
    def __init__(self, **kwargs):
        #kwargs["toolbar_control"] = False
        super().__init__(**kwargs)
        for layer in self.layers:
            self.remove_layer(layer)
            #layer.visible = False
        # mass_url = 'https://tiles.arcgis.com/tiles/hGdibHYSPO59RG1h/arcgis/rest/services/USGS_Orthos_2019/MapServer/WMTS/tile/1.0.0/USGS_Orthos_2019/default/default028mm/{z}/{y}/{x}'
        # self.add_tile_layer(url=mass_url, 
        #                     name="2019 Orthos WMTS", 
        #                     attribution="MassGIS",
        #                     max_native_zoom=20,
        #                     min_native_zoom=20,
        #                     min_zoom=19)
        for year in years:
            url = f'http://140.232.230.80:8600/static/public/{year}/tiles/{{z}}/{{x}}/{{y}}.png'
            self.add_tile_layer(url=url, 
                            name=f"{year} Orthos", 
                            attribution="MassGIS",
                            max_native_zoom=21,
                            min_native_zoom=21,
                            min_zoom=19)
        add_widgets(self, data_dir, styledict, hover_style_dict)


@solara.component
def TilePreloaderFromChip(chip_gdf):
    if chip_gdf is None or chip_gdf.empty:
        return
    bounds = chip_gdf.to_crs(4326).iloc[0].geometry.bounds
    tile_coords = bbox_to_tiles(bounds, zoom=21)
    tile_urls = []
    for year in years:
        for z, x, y in tile_coords:
            tile_url = f'http://140.232.230.80:8600/static/public/{year}/tiles/{{z}}/{{x}}/{{y}}.png'
            tile_urls.append(tile_url)

    html_content = (
        "<div style='display:none;'>"
        + "\n".join([f"<img src='{url}' />" for url in tile_urls])
        + "</div>"
    )
    return solara.HTML(tag="div", unsafe_innerHTML=html_content)

@solara.component
def Page():
    router = solara.use_router()

    # This function doesn't use its argument 'b', so we can remove it.
    def mark_chip_pending():
        chip_id = current_chip.value.iloc[0]['id']
        # Update chip status to labeled in tracker
        chips = pd.read_csv(data_dir / 'chip_tracker.csv')
        chip_idx = chips[chips['id'] == chip_id].index
        if len(chip_idx) > 0:
            chips.loc[chip_idx, 'status'] = 'pending'
            chips.to_csv(data_dir / 'chip_tracker.csv', index=False)
            print(f"Chip {chip_id} marked as pending.")

    def exit_interface():
        mark_chip_pending()
        router.push("/")

    with solara.Column(style={"min-width": "500px"}):
        LabelMap.element(
            zoom=zoom.value,
            on_zoom=zoom.set,
            center=center.value,
            on_center=center.set,
            scroll_wheel_zoom=True,
            toolbar_ctrl=False,
            data_ctrl=False,
            height="780px"   
        )

        solara.Button("Exit", on_click=exit_interface),

    
        # # Preload tiles for all chips in the buffer
        # if chip_buffer.value:
        #     for chip_gdf in chip_buffer.value:
        #         TilePreloaderFromChip(chip_gdf)
    