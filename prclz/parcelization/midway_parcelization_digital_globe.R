
# Set up environment ------------------------------------------------------
library(sf)
library(tidyr)
library(dplyr)
library(purrr)
library(lwgeom)
library(stringr)

library(parallel)
library(foreach)
library(doParallel)
#cl <- parallel::makeCluster(28)
#doParallel::registerDoParallel(cores=(Sys.getenv("SLURM_NTASKS_PER_NODE")))
#mcoptions = list(cores = (Sys.getenv("SLURM_NTASKS_PER_NODE")), preschedule=TRUE)
doParallel::registerDoParallel(cores=(Sys.getenv("SLURM_NTASKS_PER_NODE", unset = "1")))
mcoptions = list(cores = (Sys.getenv("SLURM_NTASKS_PER_NODE", unset = "1")), preschedule=TRUE)

#library(future)
#library(doFuture)
#library(future.batchtools)

# plan(list(tweak(batchtools_slurm, 
#                   template = "batchtools_slurm.tmpl", 
#                   label = paste0('job_',make.names(Sys.time())),
#                   resources = list(partition='broadwl',
#                                    walltime='01:00:00',
#                                    mem_per_cpu = '8G', 
#                                    nodes = '1', 
#                                    ntasks = '28',
#                                    mail = 'nmarchio@uchicago.edu',
#                                    pi_account = 'pi-bettencourt'),
#                   workers = 28), 
#             multiprocess))

# Parcelization function ------------------------------------------------


# Extract block parcels ------------------------------------------------
#' @param footprints, multirow dataframe, MULTIPOLYGON Simple feature collection of building footprints at country level
#' @param block, singlerow dataframe, POLYGON Simple feature collection
#' @param ptdist, meters between points to control how closely parcels conform to buildings
#' 
#' @return MULTILINE Simple feature collection
#'  
st_parcelize <- function(footprints, block, ptdist){
  message(paste0('Block ',block$block_id,' - ',nrow(footprints),' buildings (',ptdist,'m parcel resolution)'))
  if (nrow(footprints) > 0) { 
    # Extract building polygons within specified block
    block_footprints <- footprints %>% 
      sf::st_convex_hull() %>%
      sf::st_difference() %>%
      lwgeom::st_make_valid() %>%
      sf::st_cast(to = "MULTIPOLYGON")
    # Convert building polygons to lines
    parcels = block_footprints %>%
      lwgeom::st_make_valid() %>%
      sf::st_union() %>% 
      sf::st_cast(., "POLYGON") %>% 
      sf::st_sf() %>%
      sf::st_cast(., "LINESTRING") %>%
      dplyr::mutate(id = row_number())
    # Add points along lines and cast to points
    parcelpoints = st_segmentize(parcels, units::set_units(ptdist,m)) %>%
      sf::st_cast(., "MULTIPOINT") %>%
      sf::st_sf() %>%
      dplyr::mutate(id = parcels$id)
    # Voronoi polygon tesselation
    parcel_voronoi <- parcelpoints %>% sf::st_union() 
    parcel_voronoi <- {suppressWarnings(sf::st_voronoi(parcel_voronoi, envelope = sf::st_geometry(block)))} 
    parcel_voronoi <- parcel_voronoi %>% sf::st_cast() 
    parcel_voronoi <- {suppressMessages(sf::st_intersection(x = parcel_voronoi, y = block))} 
    parcel_voronoi <- parcel_voronoi %>%  sf::st_sf()
    # Join with building ID
    parcel_voronoi <- {suppressMessages(sf::st_join(x = parcel_voronoi, y = parcelpoints))} 
    parcel_voronoi <- parcel_voronoi %>% tidyr::fill(id) 
    # Group by the parcel ID to dissolve geometries 
    parcel_voronoi = raster::aggregate(parcel_voronoi, list(ID = parcel_voronoi$id), raster::unique)
    # Convert it back to lines
    parcel_grid = parcel_voronoi %>% 
      sf::st_cast("MULTILINESTRING") %>% 
      sf::st_geometry() %>% 
      sf::st_sf() %>%
      sf::st_difference() %>% 
      sf::st_union() %>% 
      sf::st_sf() %>%
      dplyr::mutate(block_id = block$block_id)
    return(parcel_grid)
  }
  else {
    parcel_grid = block %>% sf::st_cast("MULTILINESTRING") %>% dplyr::select(block_id) 
  }
}

#!/usr/bin/env Rscript

# Read in command line argument containing building file path
args = R.utils::commandArgs(asValues=TRUE)
buildings_file <- args['building']

# Show path in terminal
cat(sprintf("Reading buildings %s\n",buildings_file))

# Parsing building path into blocks (input) and parcels (output) paths
# [COOPER] to accomodate Digital Globe just operate in parallel directories
#file_parse <- stringr::str_match_all(buildings_file, "data/buildings/(.*?)/(.*?)/buildings_(.*?).geojson")
file_parse <- stringr::str_match_all(buildings_file, "data/dg_buildings/(.*?)/(.*?)/buildings_(.*?).geojson")
blocks_file <- paste0('data/blocks/',file_parse[[1]][2],'/',file_parse[[1]][3],'/blocks_',file_parse[[1]][4],'.csv')
#parcels_file <- paste0('data/parcels/',file_parse[[1]][2],'/',file_parse[[1]][3],'/parcels_',file_parse[[1]][4],'.geojson')
parcels_file <- paste0('data/dg_parcels/',file_parse[[1]][2],'/',file_parse[[1]][3],'/parcels_',file_parse[[1]][4],'.geojson')

# Load blocks and buildings spatial dataframes
sf_df_blocks <- sf::st_read(blocks_file) %>% 
  sf::st_as_sf(., wkt = 'geometry') %>% 
  sf::st_set_crs(sf::st_crs(4326)) %>%
  lwgeom::st_make_valid()
sf_df_buildings <- sf::st_read(buildings_file) %>%
  lwgeom::st_make_valid()

# Join block groupings into buildings spatial dataframes
sf_df <- sf::st_join(x = sf_df_buildings, y = sf_df_blocks, largest = TRUE) %>% 
  dplyr::select(osm_id, block_id) %>%
  lwgeom::st_make_valid()

# Split buildings and blocks
split_buildings <- split(sf_df, sf_df$block_id) 
split_blocks <- split(sf_df_blocks, sf_df_blocks$block_id) 

# Parallelize computation across blocks to generate parcel geometries 
# 1st attempt 1m resolution, 2nd attempt 100m resolution, then give up and inherit empty block geometry)
sf_df_parcels <- foreach::foreach(i=split_buildings, j = split_blocks, .combine=rbind, .options.multicore=mcoptions) %dopar% 
  tryCatch({
    st_parcelize(footprints = i, block = j, ptdist = 1)
  }, error=function(e) {
    p1 <- try(st_parcelize(footprints = i, block = j, ptdist = 100))
    if(class(p1) == "try-error") {
      p1 <- j %>% sf::st_cast("MULTILINESTRING") %>% dplyr::select(block_id) 
    }
    return(p1)}
  )

# Write GADM-level spatial df containing block-level parcels
sf::st_write(obj = sf_df_parcels, dsn = paste0(parcels_file), delete_dsn = TRUE)

#parallel::stopCluster(cl)
