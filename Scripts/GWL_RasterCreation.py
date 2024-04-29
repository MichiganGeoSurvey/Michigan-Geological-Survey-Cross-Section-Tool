# *****************************************************
# *****************************************************
# GWL_RasterCreation.py
# Version: 0.1
# Date: 09/08/2023
# Original Author: Matthew Bell, Michigan Geological Survey, matthew.e.bell@wmich.edu
# Description: ArcToolbox tool script to transform groundwater data into multiple raster surfaces
# *****************************************************
# *****************************************************

import arcpy
import os
import sys
import datetime

# Functions
# ******************************************************
def checkExtensions():
    # Check for the Spatial Analyst Extension
    try:
        if arcpy.CheckExtension("Spatial") == "Available":
            arcpy.CheckOutExtension("Spatial")
        else:
            raise "LicenseError"
    except "LicenseError":
        arcpy.AddMessage("Spatial Analyst extension is unavailable")
        raise SystemError

def createGWLraster(points,outraster,boundary):
    if int(arcpy.management.GetCount(points)[0]) < 10:
        arcpy.AddMessage("  *Not enough datapoints for the given time period. (At least 10 needed) Skipping time interval...*")
        pass
    else:
        with arcpy.EnvManager(mask=boundary):
            out_raster = arcpy.sa.Idw(
                in_point_features=points,
                z_field="SWL_ELEV",
                cell_size=10,
                power=2,
                search_radius="VARIABLE 12",
                in_barrier_polyline_features=None)
        out_raster.save(outraster)
        mp.addDataFromPath(outraster)
        prj.save()
    arcpy.management.SelectLayerByAttribute(points,"CLEAR_SELECTION")

# Parameters
# *******************************************************
# Surface DEM
gwlWW = arcpy.GetParameterAsText(0)

# Project extent
featExtent = arcpy.GetParameterAsText(1)

# Output Water Feature
locRaster = arcpy.GetParameterAsText(2)

# Designation for Types of Wells to Review
wellType = arcpy.GetParameterAsText(3)

# Custom Range Boolean
customRange = arcpy.GetParameterAsText(4)

# List of defined date-ranges
dateRange = arcpy.ValueTable(2)
dateRange.loadFromString(arcpy.GetParameterAsText(5))

# Local Variables
# *******************************************************
wkt = "PROJCS['NAD_1983_Hotine_Oblique_Mercator_Azimuth_Natural_Origin',GEOGCS['GCS_North_American_1983',DATUM['D_North_American_1983',SPHEROID['GRS_1980',6378137.0,298.257222101]],PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]],PROJECTION['Hotine_Oblique_Mercator_Azimuth_Natural_Origin'],PARAMETER['False_Easting',2546731.496],PARAMETER['False_Northing',-4354009.816],PARAMETER['Scale_Factor',0.9996],PARAMETER['Azimuth',337.25556],PARAMETER['Longitude_Of_Center',-86.0],PARAMETER['Latitude_Of_Center',45.30916666666666],UNIT['Meter',1.0]]"

# Begin
# *******************************************************
# Check for the Spatial Analyst Extension
checkExtensions()

# Establishing Spatial Reference
sr = arcpy.SpatialReference(text=wkt)

# Environment Variables
arcpy.env.overwriteOutput = True
scratchDir = arcpy.env.scratchWorkspace
arcpy.env.workspace = scratchDir
arcpy.AddMessage("Scratch Space: " + scratchDir)
arcpy.env.outputCoordinateSystem = sr
prj = arcpy.mp.ArcGISProject("CURRENT")
mp = prj.activeMap

arcpy.AddMessage("BEGIN CREATING GROUNDWATER RASTER SURFACES FOR THE AREA...")
arcpy.AddMessage(" - Types of wells being analyzed: {}".format(wellType))
if wellType == "All Wells":
    if customRange == "true":
        try:
            try:
                allYears = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_AllYears")
                createGWLraster(points=gwlWW, outraster=allYears, boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-1: Failed to create 'All Years' raster")
                raise SystemError
            try:
                dateInterval = []
                for i in range(0,dateRange.rowCount):
                    startDate = dateRange.getValue(i,0)
                    endDate = dateRange.getValue(i,1)
                    beginningYear = int(startDate)
                    endingYear = int(endDate)

                    # Create a generic date object. The values are not important, just that the object is created to replace with
                    # the beginning year
                    genDate = datetime.datetime(year=1900, month=1, day=1)
                    date1 = genDate.replace(year=beginningYear).strftime('%Y-%m-%d %H:%M:%S')
                    date2 = genDate.replace(year=endingYear,month=12,day=31).strftime('%Y-%m-%d %H:%M:%S')
                    dateInterval.append([date1, date2])
                for date in dateInterval:
                    arcpy.AddMessage("Beginning: {}, Ending: {}".format(date[0], date[1]))
                    firstDate = datetime.datetime.strptime(date[0], '%Y-%m-%d %H:%M:%S')
                    secondDate = datetime.datetime.strptime(date[1], '%Y-%m-%d %H:%M:%S')
                    firstYear = int(firstDate.year)
                    secondYear = int(secondDate.year)
                    rasterProject = os.path.join(locRaster,
                                                 os.path.splitext(os.path.basename(gwlWW))[0] + "_{}_{}".format(
                                                     firstYear,
                                                     secondYear))
                    selectWells = arcpy.management.SelectLayerByAttribute(
                        in_layer_or_view=gwlWW,
                        selection_type="NEW_SELECTION",
                        where_clause="CONST_DATE >= timestamp '{}' And CONST_DATE <= timestamp '{}'".format(date[0],
                                                                                                         date[1]),
                        invert_where_clause=None)
                    createGWLraster(points=selectWells,
                                    outraster=rasterProject,
                                    boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-2: Failed to create other custom time range rasters")
                raise SystemError
        except:
            arcpy.AddError("ERROR 038: Failed to create groundwater rasters")
            raise SystemError
    else:
        try:
            try:
                allYears = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_AllYears")
                createGWLraster(points=gwlWW, outraster=allYears, boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-1: Failed to create 'All Years' raster")
                raise SystemError
            try:
                pre2000s = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_Pre2000s")
                selctPre2000s = arcpy.management.SelectLayerByAttribute(
                    in_layer_or_view=gwlWW,
                    selection_type="NEW_SELECTION",
                    where_clause="CONST_DATE < timestamp '2000-01-01 00:00:00'",
                    invert_where_clause=None)
                createGWLraster(points=selctPre2000s, outraster=pre2000s, boundary=featExtent)
                dateInterval = []
                currentTime = datetime.datetime.now()
                beginningYear = 2000
                endingYear = int(currentTime.year)
                for i in range(beginningYear, endingYear, 5):
                    year1 = i
                    year2 = i + 5
                    # Create a generic date object. The values are not important, just that the object is created to replace with
                    # the beginning year
                    genDate = datetime.datetime(year=1900, month=1, day=1)
                    if i == beginningYear:
                        date1 = genDate.replace(year=year1).strftime('%Y-%m-%d %H:%M:%S')
                        date2 = genDate.replace(year=year2, month=12, day=31).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        if genDate.replace(year=year1,month=12,day=31).strftime('%Y-%m-%d %H:%M:%S') in dateInterval[-1][1]:
                            date1 = genDate.replace(year=year1 + 1).strftime('%Y-%m-%d %H:%M:%S')
                            date2 = genDate.replace(year=year2, month=12, day=31).strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            date1 = genDate.replace(year=year1).strftime('%Y-%m-%d %H:%M:%S')
                            date2 = genDate.replace(year=year2, month=12, day=31).strftime('%Y-%m-%d %H:%M:%S')
                    dateInterval.append([date1, date2])
                for date in dateInterval:
                    arcpy.AddMessage("Beginning: {}, Ending: {}".format(date[0], date[1]))
                    firstDate = datetime.datetime.strptime(date[0], '%Y-%m-%d %H:%M:%S')
                    secondDate = datetime.datetime.strptime(date[1], '%Y-%m-%d %H:%M:%S')
                    firstYear = int(firstDate.year)
                    secondYear = int(secondDate.year)
                    rasterProject = os.path.join(locRaster,
                                                 os.path.splitext(os.path.basename(gwlWW))[0] + "_{}_{}".format(
                                                     firstYear,
                                                     secondYear))
                    selectWells = arcpy.management.SelectLayerByAttribute(
                        in_layer_or_view=gwlWW,
                        selection_type="NEW_SELECTION",
                        where_clause="CONST_DATE >= timestamp '{}' And CONST_DATE <= timestamp '{}'".format(date[0],
                                                                                                         date[1]),
                        invert_where_clause=None)
                    createGWLraster(points=selectWells, outraster=rasterProject, boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-2: Failed to create other custom time range rasters")
                raise SystemError
        except:
            arcpy.AddError("ERROR 038: Failed to create groundwater rasters")
            raise SystemError
elif wellType == "Bedrock Wells":
    if customRange == "true":
        try:
            try:
                allYears = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_AllYears_BDRK")
                selectWellsBDRK = arcpy.management.SelectLayerByAttribute(
                    in_layer_or_view=gwlWW,
                    selection_type="NEW_SELECTION",
                    where_clause="AQ_TYPE = 'ROCK'",
                    invert_where_clause=None)
                createGWLraster(points=selectWellsBDRK, outraster=allYears, boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-1: Failed to create 'All Years' raster")
                raise SystemError
            try:
                dateInterval = []
                for i in range(0, dateRange.rowCount):
                    startDate = dateRange.getValue(i, 0)
                    endDate = dateRange.getValue(i, 1)
                    beginningYear = int(startDate)
                    endingYear = int(endDate)

                    # Create a generic date object. The values are not important, just that the object is created to replace with
                    # the beginning year
                    genDate = datetime.datetime(year=1900, month=1, day=1)
                    date1 = genDate.replace(year=beginningYear).strftime('%Y-%m-%d %H:%M:%S')
                    date2 = genDate.replace(year=endingYear,month=12,day=31).strftime('%Y-%m-%d %H:%M:%S')
                    dateInterval.append([date1, date2])
                for date in dateInterval:
                    arcpy.AddMessage("Beginning: {}, Ending: {}".format(date[0], date[1]))
                    firstDate = datetime.datetime.strptime(date[0], '%Y-%m-%d %H:%M:%S')
                    secondDate = datetime.datetime.strptime(date[1], '%Y-%m-%d %H:%M:%S')
                    firstYear = int(firstDate.year)
                    secondYear = int(secondDate.year)
                    rasterProject = os.path.join(locRaster,
                                                 os.path.splitext(os.path.basename(gwlWW))[0] + "_{}_{}_BDRK".format(
                                                     firstYear,
                                                     secondYear))
                    selectWells = arcpy.management.SelectLayerByAttribute(
                        in_layer_or_view=gwlWW,
                        selection_type="NEW_SELECTION",
                        where_clause="AQ_TYPE = 'ROCK' And CONST_DATE >= timestamp '{}' And CONST_DATE <= timestamp '{}'".format(
                            date[0], date[1]),
                        invert_where_clause=None)
                    createGWLraster(points=selectWells,
                                    outraster=rasterProject,
                                    boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-2: Failed to create other custom time range rasters")
                raise SystemError
        except:
            arcpy.AddError("ERROR 038: Failed to create groundwater rasters")
            raise SystemError
    else:
        try:
            try:
                allYears = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_AllYears_BDRK")
                selectWellsBDRK = arcpy.management.SelectLayerByAttribute(
                    in_layer_or_view=gwlWW,
                    selection_type="NEW_SELECTION",
                    where_clause="AQ_TYPE = 'ROCK'",
                    invert_where_clause=None)
                createGWLraster(points=selectWellsBDRK, outraster=allYears, boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-1: Failed to create 'All Years' raster")
                raise SystemError
            try:
                pre2000s = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_Pre2000s_BDRK")
                selctPre2000s = arcpy.management.SelectLayerByAttribute(
                    in_layer_or_view=gwlWW,
                    selection_type="NEW_SELECTION",
                    where_clause="AQ_TYPE = 'ROCK' And CONST_DATE < timestamp '2000-01-01 00:00:00'",
                    invert_where_clause=None)
                createGWLraster(points=selctPre2000s, outraster=pre2000s, boundary=featExtent)
                dateInterval = []
                currentTime = datetime.datetime.now()
                beginningYear = 2000
                endingYear = int(currentTime.year)
                for i in range(beginningYear, endingYear, 5):
                    year1 = i
                    year2 = i + 5
                    # Create a generic date object. The values are not important, just that the object is created to replace with
                    # the beginning year
                    genDate = datetime.datetime(year=1900, month=1, day=1)
                    if i == beginningYear:
                        date1 = genDate.replace(year=year1).strftime('%Y-%m-%d %H:%M:%S')
                        date2 = genDate.replace(year=year2, month=12, day=31).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        if genDate.replace(year=year1, month=12, day=31).strftime('%Y-%m-%d %H:%M:%S') in \
                                dateInterval[-1][1]:
                            date1 = genDate.replace(year=year1 + 1).strftime('%Y-%m-%d %H:%M:%S')
                            date2 = genDate.replace(year=year2, month=12, day=31).strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            date1 = genDate.replace(year=year1).strftime('%Y-%m-%d %H:%M:%S')
                            date2 = genDate.replace(year=year2, month=12, day=31).strftime('%Y-%m-%d %H:%M:%S')
                    dateInterval.append([date1, date2])
                for date in dateInterval:
                    arcpy.AddMessage("Beginning: {}, Ending: {}".format(date[0], date[1]))
                    firstDate = datetime.datetime.strptime(date[0], '%Y-%m-%d %H:%M:%S')
                    secondDate = datetime.datetime.strptime(date[1], '%Y-%m-%d %H:%M:%S')
                    firstYear = int(firstDate.year)
                    secondYear = int(secondDate.year)
                    rasterProject = os.path.join(locRaster,
                                                 os.path.splitext(os.path.basename(gwlWW))[0] + "_{}_{}_BDRK".format(
                                                     firstYear,
                                                     secondYear))
                    selectWells = arcpy.management.SelectLayerByAttribute(
                        in_layer_or_view=gwlWW,
                        selection_type="NEW_SELECTION",
                        where_clause="AQ_TYPE = 'ROCK' And CONST_DATE >= timestamp '{}' And CONST_DATE <= timestamp '{}'".format(date[0],
                                                                                                           date[1]),
                        invert_where_clause=None)
                    createGWLraster(points=selectWells, outraster=rasterProject, boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-2: Failed to create other custom time range rasters")
                raise SystemError
        except:
            arcpy.AddError("ERROR 038: Failed to create groundwater rasters")
            raise SystemError
elif wellType == "Drift Wells":
    if customRange == "true":
        try:
            try:
                allYears = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_AllYears_DRIFT")
                selectWellsDRIFT = arcpy.management.SelectLayerByAttribute(
                    in_layer_or_view=gwlWW,
                    selection_type="NEW_SELECTION",
                    where_clause="AQ_TYPE = 'DRIFT'",
                    invert_where_clause=None)
                createGWLraster(points=selectWellsDRIFT, outraster=allYears, boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-1: Failed to create 'All Years' raster")
                raise SystemError
            try:
                dateInterval = []
                for i in range(0, dateRange.rowCount):
                    startDate = dateRange.getValue(i, 0)
                    endDate = dateRange.getValue(i, 1)
                    beginningYear = int(startDate)
                    endingYear = int(endDate)

                    # Create a generic date object. The values are not important, just that the object is created to replace with
                    # the beginning year
                    genDate = datetime.datetime(year=1900, month=1, day=1)
                    date1 = genDate.replace(year=beginningYear).strftime('%Y-%m-%d %H:%M:%S')
                    date2 = genDate.replace(year=endingYear,month=12,day=31).strftime('%Y-%m-%d %H:%M:%S')
                    dateInterval.append([date1, date2])
                for date in dateInterval:
                    arcpy.AddMessage("Beginning: {}, Ending: {}".format(date[0], date[1]))
                    firstDate = datetime.datetime.strptime(date[0], '%Y-%m-%d %H:%M:%S')
                    secondDate = datetime.datetime.strptime(date[1], '%Y-%m-%d %H:%M:%S')
                    firstYear = int(firstDate.year)
                    secondYear = int(secondDate.year)
                    rasterProject = os.path.join(locRaster,
                                                 os.path.splitext(os.path.basename(gwlWW))[0] + "_{}_{}_DRIFT".format(
                                                     firstYear,
                                                     secondYear))
                    selectWells = arcpy.management.SelectLayerByAttribute(
                        in_layer_or_view=gwlWW,
                        selection_type="NEW_SELECTION",
                        where_clause="AQ_TYPE = 'DRIFT' And CONST_DATE >= timestamp '{}' And CONST_DATE <= timestamp '{}'".format(
                            date[0], date[1]),
                        invert_where_clause=None)
                    createGWLraster(points=selectWells,
                                    outraster=rasterProject,
                                    boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-2: Failed to create other custom time range rasters")
                raise SystemError
        except:
            arcpy.AddError("ERROR 038: Failed to create groundwater rasters")
            raise SystemError
    else:
        try:
            try:
                allYears = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_AllYears_BDRK")
                selectWellsDRIFT = arcpy.management.SelectLayerByAttribute(
                    in_layer_or_view=gwlWW,
                    selection_type="NEW_SELECTION",
                    where_clause="AQ_TYPE = 'DRIFT'",
                    invert_where_clause=None)
                createGWLraster(points=selectWellsDRIFT, outraster=allYears, boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-1: Failed to create 'All Years' raster")
                raise SystemError
            try:
                pre2000s = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_Pre2000s_DRIFT")
                selctPre2000s = arcpy.management.SelectLayerByAttribute(
                    in_layer_or_view=gwlWW,
                    selection_type="NEW_SELECTION",
                    where_clause="AQ_TYPE = 'DRIFT' And CONST_DATE < timestamp '2000-01-01 00:00:00'",
                    invert_where_clause=None)
                createGWLraster(points=selctPre2000s, outraster=pre2000s, boundary=featExtent)
                dateInterval = []
                currentTime = datetime.datetime.now()
                beginningYear = 2000
                endingYear = int(currentTime.year)
                for i in range(beginningYear, endingYear, 5):
                    year1 = i
                    year2 = i + 5
                    # Create a generic date object. The values are not important, just that the object is created to replace with
                    # the beginning year
                    genDate = datetime.datetime(year=1900, month=1, day=1)
                    if i == beginningYear:
                        date1 = genDate.replace(year=year1).strftime('%Y-%m-%d %H:%M:%S')
                        date2 = genDate.replace(year=year2, month=12, day=31).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        if genDate.replace(year=year1, month=12, day=31).strftime('%Y-%m-%d %H:%M:%S') in \
                                dateInterval[-1][1]:
                            date1 = genDate.replace(year=year1 + 1).strftime('%Y-%m-%d %H:%M:%S')
                            date2 = genDate.replace(year=year2, month=12, day=31).strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            date1 = genDate.replace(year=year1).strftime('%Y-%m-%d %H:%M:%S')
                            date2 = genDate.replace(year=year2, month=12, day=31).strftime('%Y-%m-%d %H:%M:%S')
                    dateInterval.append([date1, date2])
                for date in dateInterval:
                    arcpy.AddMessage("Beginning: {}, Ending: {}".format(date[0], date[1]))
                    firstDate = datetime.datetime.strptime(date[0], '%Y-%m-%d %H:%M:%S')
                    secondDate = datetime.datetime.strptime(date[1], '%Y-%m-%d %H:%M:%S')
                    firstYear = int(firstDate.year)
                    secondYear = int(secondDate.year)
                    rasterProject = os.path.join(locRaster,
                                                 os.path.splitext(os.path.basename(gwlWW))[0] + "_{}_{}_DRIFT".format(
                                                     firstYear,
                                                     secondYear))
                    selectWells = arcpy.management.SelectLayerByAttribute(
                        in_layer_or_view=gwlWW,
                        selection_type="NEW_SELECTION",
                        where_clause="AQ_TYPE = 'DRIFT' And CONST_DATE >= timestamp '{}' And CONST_DATE <= timestamp '{}'".format(
                            date[0],
                            date[1]),
                        invert_where_clause=None)
                    createGWLraster(points=selectWells, outraster=rasterProject, boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-2: Failed to create other custom time range rasters")
                raise SystemError
        except:
            arcpy.AddError("ERROR 038: Failed to create groundwater rasters")
            raise SystemError