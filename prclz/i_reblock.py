import typing
from typing import List, Tuple  

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon, MultiLineString, Point, LineString
from shapely.ops import cascaded_union, polygonize
from shapely.wkt import loads, dumps
import pandas as pd
import numpy as np 
import time 

import os 
import matplotlib.pyplot as plt 
import sys 

import argparse
import igraph

import i_topology_utils
from i_topology import *
import time 
import tqdm 

ROOT = "../"
DATA = os.path.join(ROOT, "data")
TRANS_TABLE = pd.read_csv(os.path.join(ROOT, "data_processing", 'country_codes.csv'))


def add_buildings(graph: PlanarGraph, buildings: List[Tuple]):

    total_blgds = len(buildings)
    #print("\t\tbuildings....")
    for i, bldg_node in enumerate(buildings):
        graph.add_node_to_closest_edge(bldg_node, terminal=True)

    if total_blgds > 0:
        graph.cleanup_linestring_attr()
    return graph 

def clean_graph(graph):
    is_conn = graph.is_connected()
    if is_conn:
        #print("Graph is connected")
        return graph, 1
    else:
        components = graph.components(mode=igraph.WEAK)
        num_components = len(components)
        #print("--DISCONNECTED: has {} components".format(num_components))
        comp_sizes = [len(idxs) for idxs in components]
        arg_max = np.argmax(comp_sizes)
        comp_indices = components[arg_max]

        return graph.subgraph(comp_indices), num_components

def get_optimal_path(graph: PlanarGraph, buildings: List[Tuple], simplify: bool=False, verbose: bool=False):
    '''
    Given a graph of the Parcel and the corresponding list of buildings (expressed as a list of tuple pairs),
    does the reblocking
    '''

    # Step 1: add the buildings to the PlanarGraph
    start = time.time()
    graph = add_buildings(graph, buildings)
    bldg_time = time.time() - start

    # Step 2: clean the graph if it's disconnected
    graph, num_components = clean_graph(graph)

    node_count_pre = len(graph.vs)
    edge_count_pre = len(graph.es)

    # Step 3: do the Steiner Tree approx
    if simplify:
        start = time.time()
        graph.simplify()
        simplify_time = time.time() - start 
        node_count_post = len(graph.vs)
        edge_count_post = len(graph.es)
    else:
        simplify_time = 0
        node_count_post = node_count_pre 
        edge_count_post = edge_count_pre
        
    start = time.time()
    graph.steiner_tree_approx()
    steiner_time = time.time() - start 

    # Step 4: convert the stiener edges and terminal nodes to linestrings and points, respecitvely
    #steiner_lines = graph.get_steiner_linestrings()
    new_steiner, existing_steiner = graph.get_steiner_linestrings()
    terminal_points = graph.get_terminal_points()
        # summary_columns = [      'bldg_time',       'simplify_time',     'steiner_time', 'num_graph_comps',  
        #                     'node_count_pre',     'node_count_post',   'edge_count_pre', 'edge_count_post',
        #                         'bldg_count',    'num_block_coords', 'num_block_coords_unmatched',  'block']

    if verbose:
        summary = [bldg_time, simplify_time, steiner_time, num_components, node_count_pre, node_count_post, edge_count_pre, edge_count_post]
        return new_steiner, existing_steiner, terminal_points, summary 
    else:
        return new_steiner, existing_steiner, terminal_points

class CheckPointer:
    '''
    Small container class which handles saving of work, checking if
    prior work exists, etc
    '''

    def __init__(self, region: str, gadm: str, gadm_code: str, drop_already_completed: bool):

        self.reblock_path = os.path.join(DATA, "reblock", region, gadm_code)
        if not os.path.exists(self.reblock_path):
            os.makedirs(self.reblock_path)
        self.summary_path = os.path.join(self.reblock_path, "reblock_summary_{}.csv".format(gadm))
        self.steiner_path = os.path.join(self.reblock_path, "steiner_lines_{}.csv".format(gadm))
        self.terminal_path = os.path.join(self.reblock_path, "terminal_points_{}.csv".format(gadm))

        self.prior_work_exists = (os.path.exists(self.summary_path)) and drop_already_completed

        self.summary_dict, self.steiner_lines_dict, self.terminal_points_dict = self.load_dicts()
        self.completed = set(self.summary_dict.keys())
        if self.prior_work_exists:
            print("--Loading {} previously computed results".format(len(self.completed)))

    def update(self, block_id, new_steiner, existing_steiner, terminal_points, summary):
        new_steiner = new_steiner if new_steiner is None else dumps(new_steiner)
        existing_steiner = existing_steiner if existing_steiner is None else dumps(existing_steiner)
        terminal_points = terminal_points if terminal_points is None else dumps(terminal_points)    
        
        self.summary_dict[block_id] = summary 
        self.terminal_points_dict[block_id] = [terminal_points, block_id]
        self.steiner_lines_dict[block_id+'new_steiner'] = [new_steiner, block_id, 'new_steiner', block_id+'new_steiner'] 
        self.steiner_lines_dict[block_id+'existing_steiner'] = [existing_steiner, block_id, 'existing_steiner', block_id+'existing_steiner'] 

    def load_dicts(self):
        if self.prior_work_exists:
            summary_records = pd.read_csv(self.summary_path).drop(['Unnamed: 0'], axis=1).to_dict('records')
            summary_dict = {d['block']:list(d.values()) for d in summary_records}

            steiner_records = pd.read_csv(self.steiner_path).drop(['Unnamed: 0'], axis=1).to_dict('records')
            steiner_dict = {d['block_w_type']:list(d.values()) for d in steiner_records}

            terminal_points_records = pd.read_csv(self.terminal_path).drop(['Unnamed: 0'], axis=1).to_dict('records')
            terminal_points_dict = {d['block']:list(d.values()) for d in terminal_points_records}
            return summary_dict, steiner_dict, terminal_points_dict
        else:
            return {}, {}, {}

    def save(self):
        summary_columns = [      'bldg_time',       'simplify_time',     'steiner_time', 'num_graph_comps',  
                            'node_count_pre',     'node_count_post',   'edge_count_pre', 'edge_count_post',
                                'bldg_count',    'num_block_coords', 'num_block_coords_unmatched',  'block']

        steiner_columns = ['geometry', 'block', 'line_type', 'block_w_type']
        terminal_columns = ['geometry', 'block']

        summary_df = pd.DataFrame.from_dict(self.summary_dict, orient='index', columns=summary_columns)
        steiner_df = pd.DataFrame.from_dict(self.steiner_lines_dict, orient='index', columns=steiner_columns)
        terminal_df = pd.DataFrame.from_dict(self.terminal_points_dict, orient='index', columns=terminal_columns)

        summary_df.to_csv(self.summary_path)
        steiner_df.to_csv(self.steiner_path)
        terminal_df.to_csv(self.terminal_path)

# def convert_to_polys(parcel_geom, eps=1e-8):

#     parcel_geom = unary_union(parcel_geom)
#     buffered = parcel_geom.buffer(eps)
#     convex_hull = parcel_geom.convex_hull
#     return convex_hull.difference(buffered)

# def get_closest_point(parcel_geom, node_geom, block_buffer):
#     '''
#     Helper function to move building centroids to the closest parcel
#     boundary, BUT that favors a parcel boundary that is a current
#     block (i.e. existing)
#     '''
#     #block_points_set = block_buffer

#     parcel_points = list(parcel_geom.exterior.coords)
#     node_points = list(node_geom.coords)[0]

#     closest_edge_nodes = []
#     closest_edge_distances = []
#     closest_block_edge_nodes = []
#     closest_block_edge_distances = []

#     assert parcel_points[0] == parcel_points[-1], "Parcel not closed -- check"
#     for i in range(1, len(parcel_points)):
#         pt0 = parcel_points[i-1]
#         pt1 = parcel_points[i]
#         edge_tuple = (pt0, pt1)

#         # print(edge_tuple)
#         # print(node_points)

#         closest_node = PlanarGraph.closest_point_to_node(edge_tuple, node_points)
#         closest_distance = distance(closest_node, node_points)

#         # Check if both points are in the block_points_set
#         #if (pt0 in block_points_set) and (pt1 in block_points_set):
#         if block_buffer.intersects(Point(pt0)) and block_buffer.intersects(Point(pt1)):
#             closest_block_edge_nodes.append(closest_node)
#             closest_block_edge_distances.append(closest_distance)          
#         # Or if they are not
#         else:
#             closest_edge_nodes.append(closest_node)
#             closest_edge_distances.append(closest_distance)               

#     # Prefer edges from the existing block
#     if len(closest_block_edge_nodes) > 0:
#         print("Found block edge!")
#         argmin = np.argmin(closest_block_edge_distances)
#         closest = closest_block_edge_nodes[argmin]
#     else:
#         print("Did not find edge...")
#         argmin = np.argmin(closest_edge_distances)
#         closest = closest_edge_nodes[argmin]
#     return closest 


def drop_buildings_intersecting_block(parcel_geom, building_list, block_geom):
    '''
    If a parcel shares a boundary with the block, then it already has access 
    and doesn't need to be included. So, polygonize the parcels and intersect 
    the parcel polygons with the boundary of the block, thus allowing reblocking
    to focus only on the interior parcels without access.
    '''

    # Converts the parcels to polygons
    parcel_geom_df = gpd.GeoDataFrame({'geometry': list(polygonize(parcel_geom))})
    parcel_geom_df = parcel_geom_df.explode()
    parcel_geom_df.reset_index(inplace=True, drop=True)

    # Make a dataframe of building points
    building_geom_df = gpd.GeoDataFrame({'geometry': [MultiPoint(building_list)]})
    building_geom_df = building_geom_df.explode()
    building_geom_df.reset_index(inplace=True, drop=True)
    building_geom_df.reset_index(inplace=True)
    building_geom_df.rename(columns={'index': 'building_id'}, inplace=True)

    # Figure out which building is in each parcel
    m = gpd.sjoin(parcel_geom_df, building_geom_df, how='left') 
    has_building = m['building_id'].notna()
    assert has_building.sum() == building_geom_df.shape[0], "Check map_points_to_parcel sjoin"
    m_has_building = m.loc[has_building]
    m_has_building = m_has_building.rename(columns={'geometry':'parcel_geom'})
    m_has_building = m_has_building.merge(building_geom_df, how='left', on='building_id')

    # Now check which parcel geoms intersect with the block
    block_boundary = block_geom.boundary 

    fn = lambda geom: geom.intersects(block_boundary)

    # And now return just the buildings that DO NOT have parcels on the border
    m_has_building['parcel_intersects_block'] = m_has_building['parcel_geom'].apply(fn)

    reblock_buildings = m_has_building[~m_has_building['parcel_intersects_block']]['geometry'].apply(lambda g: g.coords[0])
    return list(reblock_buildings.values)

# new_points = []
# for i, row in m_has_building.iterrows():
#     pgeom = row['parcel_geom']
#     ngeom = row['geometry']
#     closest = get_closest_point(pgeom, ngeom, block_buffer)
#     #closest = get_closest_point(pgeom, ngeom, block_points_set)
#     new_points.append(closest)

# # For QC
# new_geom = [Point(x) for x in new_points]
# new_buildings = gpd.GeoDataFrame({'geometry': new_geom})
# ax = orig_parcel_geom_df.plot(color='blue', alpha=.3)
# block_buffer_geom_df = gpd.GeoDataFrame({'geometry': [block_buffer]})
# block_buffer_geom_df.plot(color='blue', alpha=1, ax=ax)
# building_geom_df.plot(color='black', ax=ax)
# new_buildings.plot(color='red', ax=ax)
# plt.show()


def reblock_gadm(region, gadm_code, gadm, simplify, block_list=None, drop_already_completed=True):
    '''
    Does reblocking for an entire GADM boundary
    '''
    block_list = [] if block_list is None else block_list

    # (1) Just load our data for one GADM
    print("Begin loading of data--{}-{}".format(region, gadm))
    parcels, buildings, blocks = i_topology_utils.load_reblock_inputs(region, gadm_code, gadm) 

    buildings['in_target'] = buildings['block_id'].applys(lambda x: x not in block_list)
    buildings.sort_values(by=['in_target', 'building_count'], inplace=True)
    

    checkpoint_every = 1

    # (2) Create a checkpointer which will handle saving and restoring of past work
    checkpointer = CheckPointer(region, gadm, gadm_code, drop_already_completed)
    all_blocks = [b for b in buildings['block_id'] if b not in checkpointer.completed]

    print("\nBegin looping")
    i = 0

    # (4) Loop and process one block at-a-time
    for block_id in tqdm.tqdm(all_blocks, total=len(all_blocks)):

        parcel_geom = parcels[parcels['block_id']==block_id]['geometry'].iloc[0]
        building_list = buildings[buildings['block_id']==block_id]['buildings'].iloc[0]
        block_geom = blocks[blocks['block_id']==block_id]['geometry'].iloc[0]

        ## UPDATES: drop buildings that intersect with the block border -- they have access
        building_list = drop_buildings_intersecting_block(parcel_geom, building_list, block_geom)

        if len(building_list) <= 1:
            continue 

        # (1) Convert parcel geometry to planar graph
        planar_graph = PlanarGraph.multilinestring_to_planar_graph(parcel_geom)

        # (2) Update the edge types based on the block graph
        missing, total_block_coords = i_topology_utils.update_edge_types(planar_graph, block_geom, check=True)

        # (3) Do reblocking 
        try:
            new_steiner, existing_steiner, terminal_points, summary = get_optimal_path(planar_graph, building_list, simplify=simplify, verbose=True)
        except:
            new_steiner = None 
            existing_steiner = None 
            terminal_points = None 
            summary = [None, None, None, None, None, None, None, None]

        # Collect and store the summary info from reblocking
        summary = summary + [len(building_list), total_block_coords, missing, block_id]
        checkpointer.update(block_id, new_steiner, existing_steiner, terminal_points, summary)

        # Save out on first iteration and on checkpoint iterations
        if (i == 0) or (i % checkpoint_every == 0):
            checkpointer.save()

             
        i += 1


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Do reblocking on a GADM')
    parser.add_argument('--region', type=str, required=True, help="region to process")
    parser.add_argument('--gadm_code', type=str, required=True, help="3-digit country gadm code to process")
    parser.add_argument('--gadm', help='process this gadm')
    parser.add_argument('--simplify', help='boolean to simplify the graph or not', action='store_true')
    parser.add_argument('--blocks', dest='block_list', help='prioritize these block ids', nargs='*', type=str)


    args = parser.parse_args()
   
    reblock_gadm(**vars(args))


