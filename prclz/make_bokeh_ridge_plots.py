from numpy import linspace
from scipy.stats.kde import gaussian_kde
import pandas as pd 
from pathlib import Path 

import numpy as np 
from view import load_aoi, make_bokeh

from bokeh.io import output_file, show
from bokeh.models import ColumnDataSource, FixedTicker, PrintfTickFormatter, NumeralTickFormatter
from bokeh.plotting import figure, save
from bokeh.layouts import layout, column, gridplot, row 
from bokeh.models.annotations import Title

import statsmodels.api as sm


def ridge(category, data, scale=20):
    l = list(zip([category]*len(data), scale*data))
    l.insert(0, (category, 0))
    l.insert(1, (category, 0))
    return l

MNP = ["#0571b0", "#f7f7f7", "#f4a582", "#cc0022"]
#MNP = ["#cc0022", "#f4a582", "#f7f7f7", "#0571b0"]
PALETTE = MNP
#RANGE = [(0,1), (2,3), (4,7), (8, np.inf)]
RANGE = [1, 3, 7, np.inf]

def get_color(complexity):
    for upper, color in zip(RANGE, PALETTE):
        if complexity <= upper:
            return color 

HEIGHT = 900
WIDTH = 900



# Load main dataframe
def make_ridge_plot_w_examples(aoi_name, file_path, output_filename, add_observations=True, bandwidth=.05, block_list=[]):

    output_file(output_filename)

    max_density = 1
    probly_df = load_aoi(file_path)
    # probly_df = pd.read_csv(file_path) 
    # probly_df['bldg_density'] = max_density*probly_df['total_bldg_area_sq_km']/probly_df['block_area_km2']
    missing_compl = probly_df['complexity'].isna()
    probly_df = probly_df.loc[~missing_compl]
    probly_df_gb = probly_df.groupby('complexity')
    #print(probly_df_gb.groups.keys())

    #cats = list(reversed(probly.keys()))
    cats_int = np.arange(probly_df['complexity'].max()+1).astype('uint8')
    cats_str = ["Complexity {}".format(i) for i in cats_int]
    int_to_str = {i:s for i, s in zip(cats_int, cats_str)}
    str_to_int = {s:i for i, s in zip(cats_int, cats_str)}

    #palette = [cc.rainbow[i*15] for i in range(17)]

    #x = linspace(-20,110, 500)
    target_col = 'bldg_density'
    #x = np.linspace(-10, 10, 500)
    x = np.linspace(0,max_density,500)
    x_prime = np.concatenate([np.array([0]), x, np.array([1])])
    SCALE = .35 * max_density

    #source = ColumnDataSource(data=dict(x=x))
    source = ColumnDataSource(data=dict(x=x_prime))

    title = "Block building density and\nblock complexity: {}".format(aoi_name)
    size = 900
    p = figure(toolbar_location='above', border_fill_color='blue', border_fill_alpha=0.25, y_range=cats_str, plot_height=size, plot_width=size, x_range=(0, 1.0), title=title)
    p.title.text_font_size = '20pt'
    p.title.text_font_style = 'bold'
    p.title.text_color = 'black'

    for i, cat_s in enumerate(reversed(cats_str)):

        cat_i = str_to_int[cat_s]
        if cat_i not in probly_df_gb.groups.keys():
            p.line([0, 1], [cat_s, cat_s])
            continue 

        #if cat_i not in probly_df.groups
        cat_data = probly_df_gb.get_group(cat_i)['bldg_density'].values
        cat_x = [cat_s]*len(cat_data)
        # Add circles for observations
        if add_observations:
            p.circle(cat_data, cat_x, fill_alpha=0.5, size=5, fill_color='black')

        print("Processing cat = {}".format(cat_i))
        print("shape = {}".format(cat_data.shape))
        if cat_data.shape[0] == 1:
            p.line([0, 1], [cat_s, cat_s])
            continue 
            
        #pdf = gaussian_kde(cat_data)
        kernel_density = sm.nonparametric.KDEMultivariate(data=cat_data, var_type='c', bw=[bandwidth])
        y = ridge(cat_s, kernel_density.pdf(x), SCALE)
        source.add(y, cat_s)
        #p.patch('x', cat_s, color=palette[i], alpha=0.6, line_color="black", source=source)
        p.patch('x', cat_s, color=get_color(cat_i), alpha=0.6, line_color="black", source=source)
     

    #p00.circle('complexity', 'bldg_density', fill_alpha=0.5, size=10, hover_color="firebrick")

    p.outline_line_color = None
    #p.background_fill_color = "#efefef"

    p.xaxis.ticker = FixedTicker(ticks=list(np.linspace(0, max_density, 11)))
    #p.xaxis.formatter = PrintfTickFormatter(format="%d%%")

    p.ygrid.grid_line_color = None
    p.xgrid.grid_line_color = "#dddddd"
    #p.xgrid.ticker = p.xaxis.ticker

    p.axis.minor_tick_line_color = None
    p.axis.major_tick_line_color = None
    p.axis.axis_line_color = None
    p.xaxis[0].formatter = NumeralTickFormatter(format="0%")

    # p.yaxis.axis_label = 'Block density'
    # p.yaxis.axis_label_text_font_style = 'bold'
    # p.yaxis.axis_label_text_font_size = '14pt'
    p.yaxis.major_label_text_font_size = '12pt'
    p.yaxis.major_label_text_font_style = 'bold'
    p.yaxis.major_label_text_color = 'black'
 
    p.xaxis.axis_label = 'Block density'
    p.xaxis.axis_label_text_font_style = 'bold'
    p.xaxis.axis_label_text_font_size = '14pt'
    p.xaxis.axis_label_text_color = 'black'
    p.xaxis.major_label_text_font_size = '12pt'
    p.xaxis.major_label_text_font_style = 'bold'
    p.xaxis.major_label_text_color = 'black'

    # Add subplots
    sub_layout_list = make_block_example_grid(probly_df, HEIGHT, WIDTH, block_list)
    grid = gridplot(children=sub_layout_list, ncols=2, toolbar_location=None)

    final_layout = row([p, grid])
    show(final_layout)

    #save(final_layout, output_filename)
    # return final_layout


def make_block_example_grid(aoi_gdf, total_height, total_width, block_list ):
    '''
    Start by assuming a 2x2 grid of examples
    '''

    # Add other figs
    r = 2
    c = 2
    height = total_height // r 
    width = total_width // c 

    flat_l = []

    for i, block in enumerate(block_list):
        cur_r = i // r 
        cur_c = i % c 
        print("Plotting block {} index {} at ({},{})".format(block, i, cur_r, cur_c))
        is_block = aoi_gdf['block_id']==block 
        cur_gdf = aoi_gdf.loc[is_block]
        cur_density = cur_gdf['bldg_density'].iloc[0]
        cur_complexity = cur_gdf['complexity'].iloc[0]

        fig = make_bokeh(cur_gdf, plot_height=height, plot_width=width, bldg_alpha=1.0)
        t = Title()
        t.text = "Complexity = {} Building density = {}%".format(cur_complexity, np.round(cur_density*100))
        fig.title = t
        fig.xaxis.visible = False
        fig.yaxis.visible = False 
        fig.title.text_color = 'black' 
        # fig.ygrid.grid_line_color = None
        # fig.xgrid.grid_line_color = None
        # fig.xaxis.minor_tick_line_color = None
        # fig.xaxis.major_tick_line_color = None
        # fig.yaxis.minor_tick_line_color = None
        # fig.yaxis.major_tick_line_color = None
        # fig.axis.axis_label = None 
        # fig.axis.axis_label = None 
        # fig.grid.grid_line_color = None 

        # Add the plot to the below
        flat_l.append(fig)

    return flat_l
    #return sub_layout

# Load main dataframe
def make_ridge_plot(aoi_name, file_path, output_filename, bandwidth=.05, add_observations=True):
    #aoi_name = "Nairoi"
    #file_path = "mnp/prclz-proto/data/LandScan_Global_2018/aoi_datasets/analysis_nairobi.csv"
    #bandwidth = 0.05
    #add_observations = True
    #output_filename = 
    output_file(output_filename)

    max_density = 1
    probly_df = pd.read_csv(file_path) 
    probly_df['bldg_density'] = max_density*probly_df['total_bldg_area_sq_km']/probly_df['block_area_km2']
    missing_compl = probly_df['complexity'].isna()
    probly_df = probly_df.loc[~missing_compl]
    probly_df_gb = probly_df.groupby('complexity')
    #print(probly_df_gb.groups.keys())

    #cats = list(reversed(probly.keys()))
    cats_int = np.arange(probly_df['complexity'].max()+1).astype('uint8')
    cats_str = ["Complexity {}".format(i) for i in cats_int]
    int_to_str = {i:s for i, s in zip(cats_int, cats_str)}
    str_to_int = {s:i for i, s in zip(cats_int, cats_str)}

    #palette = [cc.rainbow[i*15] for i in range(17)]

    #x = linspace(-20,110, 500)
    target_col = 'bldg_density'
    #x = np.linspace(-10, 10, 500)
    x = np.linspace(0,max_density,500)
    x_prime = np.concatenate([np.array([0]), x, np.array([1])])
    SCALE = .35 * max_density

    #source = ColumnDataSource(data=dict(x=x))
    source = ColumnDataSource(data=dict(x=x_prime))

    title = "Building density - {}".format(aoi_name)
    p = figure(y_range=cats_str, plot_height=900, plot_width=900, x_range=(0, 1.0), title=title)

    for i, cat_s in enumerate(reversed(cats_str)):

        cat_i = str_to_int[cat_s]
        if cat_i not in probly_df_gb.groups.keys():
            continue 

        #if cat_i not in probly_df.groups
        cat_data = probly_df_gb.get_group(cat_i)['bldg_density'].values
        cat_x = [cat_s]*len(cat_data)
        # Add circles for observations
        if add_observations:
            p.circle(cat_data, cat_x, fill_alpha=0.5, size=5, fill_color='black')

        print("Processing cat = {}".format(cat_i))
        print("shape = {}".format(cat_data.shape))
        if cat_data.shape[0] == 1:
            continue 
        #pdf = gaussian_kde(cat_data)
        kernel_density = sm.nonparametric.KDEMultivariate(data=cat_data, var_type='c', bw=[bandwidth])
        y = ridge(cat_s, kernel_density.pdf(x), SCALE)
        source.add(y, cat_s)
        #p.patch('x', cat_s, color=palette[i], alpha=0.6, line_color="black", source=source)
        p.patch('x', cat_s, color=get_color(cat_i), alpha=0.6, line_color="black", source=source)
     

    #p00.circle('complexity', 'bldg_density', fill_alpha=0.5, size=10, hover_color="firebrick")

    p.outline_line_color = None
    p.background_fill_color = "#efefef"

    p.xaxis.ticker = FixedTicker(ticks=list(np.linspace(0, max_density, 11)))
    #p.xaxis.formatter = PrintfTickFormatter(format="%d%%")

    p.ygrid.grid_line_color = None
    p.xgrid.grid_line_color = "#dddddd"
    #p.xgrid.ticker = p.xaxis.ticker

    p.axis.minor_tick_line_color = None
    p.axis.major_tick_line_color = None
    p.axis.axis_line_color = None    

    #p.y_range.range_padding = 0.12
    save(p, output_filename)

aoi_dir = Path("../data/LandScan_Global_2018/aoi_datasets/")
# make_ridge_plot(aoi_name, file_path, output_filename)

aoi_names = ['Freetown', 'Monrovia', 'Kathmandu', 'Nairobi', 'Port au Prince']
stubs = ['freetown', 'greater_monrovia', 'kathmandu', 'nairobi', 'port_au_prince']
file_names = ['analysis_{}.csv'.format(n) for n in stubs]
file_paths = [aoi_dir / f for f in file_names]
output_dir = Path("./ridge_plots_examples")
output_dir.mkdir(parents=True, exist_ok=True)
output_filenames = [output_dir / (n.replace(".csv", "_ridge.html")) for n in file_names]

block_map = {
     'Nairobi': ['KEN.30.3.3_1_59', 'KEN.30.17.4_1_63', 'KEN.30.10.2_1_27', 'KEN.30.16.1_1_3'],
    'Kathmandu': ['NPL.1.1.3.31_1_343', 'NPL.1.1.3.14_1_68', 'NPL.1.1.3.31_1_3938', 'NPL.1.1.3.31_1_1253'],
    'Monrovia': ['LBR.11.2.1_1_2563', 'LBR.11.2.1_1_282', 'LBR.11.2.1_1_1360', 'LBR.11.2.1_1_271'],
    'Freetown': ['SLE.4.2.1_1_1060', 'SLE.4.2.1_1_1280', 'SLE.4.2.1_1_693', 'SLE.4.2.1_1_1870']
}

# block_map = {
#     'Freetown': ['SLE.4.2.1_1_1060', 'SLE.4.2.1_1_1280', 'SLE.4.2.1_1_693', 'SLE.4.2.1_1_1870']
# }
for aoi_name, file_path, output_filename in zip(aoi_names, file_paths, output_filenames):
    print("aoi_name = {}".format(aoi_name))
    print("file_path = {}".format(file_path))
    print("output_filename = {}".format(output_filename))
    #make_ridge_plot(aoi_name, file_path, output_filename)

    if aoi_name not in block_map.keys():
        continue
    else:
        block_list = block_map[aoi_name]
        plots = make_ridge_plot_w_examples(aoi_name, file_path, output_filename, block_list=block_list)
    break 

# aoi_gdf = load_aoi(file_path)
# total_height = 900
# total_width = 900
# missing_compl = aoi_gdf['complexity'].isna()
# aoi_gdf = aoi_gdf.loc[~missing_compl]
# block_list = list(aoi_gdf['block_id'].values[0:4])
# l = make_block_example_grid(aoi_gdf, total_height, total_width, block_list )
