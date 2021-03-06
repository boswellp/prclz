#!/bin/bash

for country in $(find data/GADM -mindepth 1 -type d | grep "MEX\|CHN\|IRN\|IND\|MYS\|PHL\|THA\|IDN\|BRA"); do 
    echo ${country} | cut -d/ -f3
    split_path=${country/GADM/GADM_split}
    mkdir -p ${split_path}
    gadm=$(ls ${country}/*.shp | python -c "import sys; print(sorted(sys.stdin.readlines())[-1].strip())")
    python ./midway/gadm_splitter.py ${gadm} ${split_path}
done 