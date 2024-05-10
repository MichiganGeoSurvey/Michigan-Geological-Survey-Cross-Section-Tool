"""
MGS_DataCreation.py
Description: ArcToolbox tool script to create a standard workspace for any Triage mapping project, along with creating the datasets formatted the same way for the cross-section tool. Specifically built for ArcGIS Pro software.
Requirements: python, ArcGIS Pro
Author: Matthew Bell, Michigan Geological Survey, matthew.e.bell@wmich.edu
Date: 2/10/2023

Last updated: 5/9/2023
"""

# Import Modules
# *******************************************************
import os
import arcpy
import requests, zipfile
from io import BytesIO
import datetime

# Functions
# *******************************************************
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
def AddMsgAndPrint(msg,severity=0):
    # Adds message (in case this is run as a tool) and also prints the message to the screen (standard output)
    print(msg)

    # Split the message on \n first, so that if it's multiple lines, a GPMessage will be added for each line
    try:
        for string in msg.split('\n'):
            # Add appropriate geoprocessing message
            if severity == 0:
                arcpy.AddMessage(string)
            elif severity == 1:
                arcpy.AddWarning(string)
            elif severity == 2:
                arcpy.AddError(string)
    except:
        pass

def firstBDRKValue(bdrkTable, origTable, relate, seq, primLith, firstBDRK):
    # The definition used to define the first bedrock unit observed in a lithology log
    # Note: This may tag units that are not true bedrock surfaces (i.e. the driller did not use the appropriate
    # term for a lithology description). Generally, this will work, just be aware of anomolous surfaces.
    statTable = os.path.join(scratchDir, os.path.splitext(os.path.basename(origTable))[0] + "_stats")
    caseFields = relate + ";AQTYPE"
    arcpy.analysis.Statistics(in_table=origTable,
                              out_table=statTable,
                              statistics_fields="{0} MIN;{0} MAX".format(seq),
                              case_field=caseFields)

    # This step separates all the lith_codes into separate tables
    arcpy.analysis.SplitByAttributes(
        Input_Table=statTable,
        Target_Workspace=scratchDir,
        Split_Fields="AQTYPE")
    bdrkStatsTable = os.path.join(scratchDir, "R")
    drftStatsTable = os.path.join(scratchDir, "D")
    nrcdStatsTable = os.path.join(scratchDir, "U")

    # Now, we need to change the names of the fields to append all the lith_code tables into the final lithology table
    # Bedrock table first...
    arcpy.management.AlterField(
        in_table=bdrkStatsTable, field="MAX_{}".format(seq), new_field_name="MAX_BDRK", new_field_alias="",
        field_length=8, field_is_nullable="NULLABLE", clear_field_alias="CLEAR_ALIAS")
    arcpy.management.AlterField(
        in_table=bdrkStatsTable, field="MIN_{}".format(seq), new_field_name="MIN_BDRK", new_field_alias="",
        field_length=8, field_is_nullable="NULLABLE", clear_field_alias="CLEAR_ALIAS")
    # Drift Table next...
    arcpy.management.AlterField(
        in_table=drftStatsTable, field="MAX_{}".format(seq), new_field_name="MAX_DRFT", new_field_alias="",
        field_length=8, field_is_nullable="NULLABLE", clear_field_alias="CLEAR_ALIAS")
    arcpy.management.AlterField(
        in_table=drftStatsTable, field="MIN_{}".format(seq), new_field_name="MIN_DRFT", new_field_alias="",
        field_length=8, field_is_nullable="NULLABLE", clear_field_alias="CLEAR_ALIAS")
    # Finally, the no records or unknown table...
    arcpy.management.AlterField(
        in_table=nrcdStatsTable, field="MAX_{}".format(seq), new_field_name="MAX_NRCD", new_field_alias="",
        field_length=8, field_is_nullable="NULLABLE", clear_field_alias="CLEAR_ALIAS")
    arcpy.management.AlterField(
        in_table=nrcdStatsTable, field="MIN_{}".format(seq), new_field_name="MIN_NRCD", new_field_alias="",
        field_length=8, field_is_nullable="NULLABLE", clear_field_alias="CLEAR_ALIAS")

    # Now, lets join all the fields together to final lithology table...
    arcpy.management.JoinField(
        in_data=bdrkTable, in_field=relate, join_table=bdrkStatsTable, join_field=relate,
        fields="MIN_BDRK;MAX_BDRK",
        fm_option="NOT_USE_FM", field_mapping=None)
    arcpy.management.JoinField(
        in_data=bdrkTable, in_field=relate, join_table=drftStatsTable, join_field=relate,
        fields="MIN_DRFT;MAX_DRFT",
        fm_option="NOT_USE_FM", field_mapping=None)
    arcpy.management.JoinField(
        in_data=bdrkTable, in_field=relate, join_table=nrcdStatsTable, join_field=relate,
        fields="MIN_NRCD;MAX_NRCD",
        fm_option="NOT_USE_FM", field_mapping=None)

    # If the sequence number of a unit is the same as the minimum value calculated previously, that unit will be assigned as the first bedrock unit.
    with arcpy.da.UpdateCursor(bdrkTable,
                               [seq, primLith, "MIN_BDRK", "MAX_BDRK", "MIN_DRFT", "MAX_DRFT", firstBDRK]) as cursor:
        for row in cursor:
            if row[1].startswith("R"):
                if row[5] is not None:
                    if (row[2] == row[0] and row[2] > row[5]):
                        row[6] = "YES"
                    elif (row[5] + 1 == row[0] and row[3] <= row[4]):
                        row[6] = "YES"
                    else:
                        row[6] = "NO"
                if row[5] is None:
                    if row[2] == row[0]:
                        row[6] = "YES"
                    else:
                        row[6] = "NO"
            # Anything that is not bedrock will have a value of "NA" or not applicable
            else:
                row[6] = "NA"
            cursor.updateRow(row)
        del row
        del cursor
    arcpy.management.DeleteField(bdrkTable,
                                 ["{}_1".format(relate), "MIN_BDRK", "MAX_BDRK", "MIN_DRFT", "MAX_DRFT", "MIN_NRCD",
                                  "MAX_NRCD"])
    arcpy.management.Delete([statTable, bdrkStatsTable, drftStatsTable, nrcdStatsTable])

def DEMSymbol(map,feature):
    lyrDEM = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    symDEM = lyrDEM.symbology
    if hasattr(symDEM, 'colorizer'):
        if symDEM.colorizer.type == 'RasterStretchColorizer':
            symDEM.colorizer.stretchType = 'PercentClip'
            symDEM.colorizer.minPercent = 1.0
            symDEM.colorizer.maxPercent = 1.0
            cr = prj.listColorRamps('Prediction')[0]
            symDEM.colorizer.colorRamp = cr
            symDEM.colorizer.minLabel = "Min: " + symDEM.colorizer.minLabel
            symDEM.colorizer.maxLabel = "Max: " + symDEM.colorizer.maxLabel
            lyrDEM.symbology = symDEM
    if lyrDEM.supports("TRANSPARENCY"):
        lyrDEM.transparency = 50
    prj.save()

def contoursSymbol(map,feature):
    field_names = [f.name for f in arcpy.ListFields(feature)]
    try:
        lyrContours = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
        symContours = lyrContours.symbology
        if hasattr(symContours,"renderer"):
            if symContours.renderer.type == "SimpleRenderer":
                symContours.updateRenderer('UniqueValueRenderer')
                symContours.renderer.fields = [field_names[5]]
                lyrContours.symbology = symContours
                for group in symContours.renderer.groups:
                    for item in group.items:
                        if item.values[0][0] == "INDEX":
                            item.symbol.applySymbolFromGallery('Contour, Topographic, Index')
                            item.label = "Index Contours"
                            lyrContours.symbology = symContours
                        else:
                            item.symbol.applySymbolFromGallery('Contour, Topographic, Intermediate')
                            item.symbol.color = {'RGB': [115, 76, 0, 100]}
                            item.label = "Intermediate Contours"
                            lyrContours.symbology = symContours
        prj.save()
    except:
        # There is a weird bug where the contours will sometimes become classified, and sometimes it can. This catches
        # the error so it passes the symbology to continue the script. Symbology is not a huge priority at the moment.
        arcpy.AddWarning("  *Feature {} does not support Unique Value Classification*".format(
            os.path.splitext(os.path.basename(feature))[0]))
        pass

def lakesSymbol(map,feature):
    lyrLake = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    symLake = lyrLake.symbology
    symLake.renderer.symbol.applySymbolFromGallery('Water (area)', 1)
    lyrLake.symbology = symLake
    prj.save()

def riverSymbol(map,feature):
    lyrRiver = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    symRiver = lyrRiver.symbology
    symRiver.renderer.symbol.outlineColor = {'RGB': [10, 147, 252, 100]}
    symRiver.renderer.symbol.outlineWidth = 1
    lyrRiver.symbology = symRiver
    prj.save()

def roadSymbol(map,feature):
    try:
        lyrRoad = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
        symRoad = lyrRoad.symbology
        symRoad.updateRenderer('UniqueValueRenderer')
        lyrRoad.symbology = symRoad

        symRoad.renderer.fields = ['NFC']
        symRoad.renderer.removeValues({"NFC": ["1", "2", "3", "4", "5", "6", "7", "0"]})
        lyrRoad.symbology = symRoad
        symRoad.renderer.addValues(
            {"National Function Classification (NFC)": symRoad.renderer.listMissingValues()[0].items})
        lyrRoad.symbology = symRoad
        for group in symRoad.renderer.groups:
            for item in group.items:
                if item.values[0][0] == "0":
                    item.symbol.color = {'RGB': [204, 204, 204, 100]}
                    item.symbol.outlineWidth = 1.5
                    item.label = "Non-Certified"
                    lyrRoad.symbology = symRoad
                elif item.values[0][0] == "1":
                    item.symbol.color = {'RGB': [0, 92, 230, 100]}
                    item.symbol.outlineWidth = 2
                    item.label = "Interstate"
                    lyrRoad.symbology = symRoad
                elif item.values[0][0] == "2":
                    item.symbol.color = {'RGB': [169, 0, 230, 100]}
                    item.symbol.outlineWidth = 1.5
                    item.label = "Other Freeway"
                    lyrRoad.symbology = symRoad
                elif item.values[0][0] == "3":
                    item.symbol.color = {'RGB': [255, 0, 0, 100]}
                    item.symbol.outlineWidth = 1.5
                    item.label = "Other Principal Arterial"
                    lyrRoad.symbology = symRoad
                elif item.values[0][0] == "4":
                    item.symbol.color = {'RGB': [56, 168, 0, 100]}
                    item.symbol.outlineWidth = 1.5
                    item.label = "Minor Arterial"
                    lyrRoad.symbology = symRoad
                elif item.values[0][0] == "5":
                    item.symbol.color = {'RGB': [255, 170, 0, 100]}
                    item.symbol.outlineWidth = 1.5
                    item.label = "Major Collector"
                    lyrRoad.symbology = symRoad
                elif item.values[0][0] == "6":
                    item.symbol.color = {'RGB': [255, 255, 0, 100]}
                    item.symbol.outlineWidth = 1.5
                    item.label = "Minor Collector"
                    lyrRoad.symbology = symRoad
                elif item.values[0][0] == "7":
                    item.symbol.color = {'RGB': [0, 0, 0, 100]}
                    item.symbol.outlineWidth = 1
                    item.label = "NFC Local"
                    lyrRoad.symbology = symRoad
            ...
        prj.save()
    except:
        arcpy.AddWarning("  *Feature {} does not support Unique Value Classification*".format(
            os.path.splitext(os.path.basename(feature))[0]))
        pass

def railSymbol(map,feature):
    lyrRail = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    symRail = lyrRail.symbology
    symRail.renderer.symbol.applySymbolFromGallery('Railroad')
    symRail.renderer.symbol.color = {'RGB': [0, 0, 0, 100]}
    lyrRail.symbology = symRail
    prj.save()

def schoolSymbol(map,feature):
    lyrSchool = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    symSchool = lyrSchool.symbology
    symSchool.renderer.symbol.applySymbolFromGallery('School', 1)
    symSchool.renderer.symbol.color = {'RGB': [0, 92, 230, 100]}
    lyrSchool.symbology = symSchool
    prj.save()

def collegeSymbol(map,feature):
    lyrCollege = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    symCollege = lyrCollege.symbology
    symCollege.renderer.symbol.applySymbolFromGallery('School', 1)
    lyrCollege.symbology = symCollege
    prj.save()

def locSymbol(map,feature):
    lyrLoc = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    symLoc = lyrLoc.symbology
    symLoc.renderer.symbol.applySymbolFromGallery('Star 3')
    symLoc.renderer.symbol.color = {'RGB': [255, 255, 0, 100]}
    symLoc.renderer.symbol.size = 15
    lyrLoc.symbology = symLoc
    prj.save()

def sectionSymbol(map,feature):
    lyrSection = map.listLayers(feature)[0]
    symSection = lyrSection.symbology
    symSection.renderer.symbol.color = {'RGB': [255, 255, 255, 0]}
    symSection.renderer.symbol.outlineColor = {'RGB': [255, 0, 0, 100]}
    symSection.renderer.symbol.outlineWidth = 0.7
    lyrSection.symbology = symSection
    prj.save()

def townSymbol(map,feature):
    lyrTown = map.listLayers(feature)[0]
    symTown = lyrTown.symbology
    symTown.renderer.symbol.applySymbolFromGallery('Dashed Black Outline (1pt)')
    symTown.renderer.symbol.outlineWidth = 2
    lyrTown.symbology = symTown
    prj.save()

def stateCSymbol(map,feature):
    lyrStateC = map.listLayers(feature)[0]
    symStateC = lyrStateC.symbology
    symStateC.renderer.symbol.color = {'RGB': [255, 255, 255, 0]}
    symStateC.renderer.symbol.outlineColor = {'RGB': [230, 0, 169, 100]}
    symStateC.renderer.symbol.outlineWidth = 2.5
    lyrStateC.symbology = symStateC
    prj.save()

def countySymbol(map,feature):
    lyrCounty = map.listLayers(feature)[0]
    symCounty = lyrCounty.symbology
    symCounty.renderer.symbol.color = {'RGB': [255, 255, 255, 0]}
    symCounty.renderer.symbol.outlineColor = {'RGB': [0, 0, 0, 100]}
    symCounty.renderer.symbol.outlineWidth = 1.5
    lyrCounty.symbology = symCounty
    prj.save()

def xsecSymbol(map,feature):
    lyrXSec = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    symXSec = lyrXSec.symbology
    symXSec.renderer.symbol.outlineColor = {'RGB': [255, 255, 255, 100]}
    symXSec.renderer.symbol.outlineWidth = 2.5
    lyrXSec.symbology = symXSec
    prj.save()

def mile2Symbol(map,feature):
    lyr2Mile = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    sym2Mile = lyr2Mile.symbology
    sym2Mile.renderer.symbol.applySymbolFromGallery('Black Outline (1pt)')
    sym2Mile.renderer.symbol.color = {'RGB': [255, 255, 255, 0]}
    sym2Mile.renderer.symbol.outlineColor = {'RGB': [168, 0, 0, 100]}
    sym2Mile.renderer.symbol.outlineWidth = 2
    lyr2Mile.symbology = sym2Mile
    prj.save()

def mile5Symbol(map,feature):
    lyr5Mile = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    sym5Mile = lyr5Mile.symbology
    sym5Mile.renderer.symbol.applySymbolFromGallery('Black Outline (1pt)')
    sym5Mile.renderer.symbol.color = {'RGB': [255, 255, 255, 0]}
    sym5Mile.renderer.symbol.outlineColor = {'RGB': [0, 92, 230, 100]}
    sym5Mile.renderer.symbol.outlineWidth = 2
    lyr5Mile.symbology = sym5Mile
    prj.save()

def extentSymbol(map,feature):
    lyrExtent = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    symExtent = lyrExtent.symbology
    symExtent.renderer.symbol.applySymbolFromGallery('Black Outline (1pt)')
    symExtent.renderer.symbol.color = {'RGB': [255, 255, 255, 0]}
    symExtent.renderer.symbol.outlineColor = {'RGB': [168, 0, 0, 100]}
    symExtent.renderer.symbol.outlineWidth = 2
    lyrExtent.symbology = symExtent
    prj.save()

def wwSymbol(map,feature):
    lyrWW = map.listLayers(os.path.splitext(os.path.basename(feature))[0])[0]
    symWW = lyrWW.symbology
    symWW.updateRenderer('UniqueValueRenderer')
    lyrWW.symbology = symWW
    symWW.renderer.fields = ['well_label']
    symWW.renderer.removeValues({"well_label": ["Drift: Type 1 Public Supply", "Drift: Type 2 Public Supply", "Drift: Type 3 Public Supply",
                                                "Drift: All Other Wells",
                                                "Bedrock: Type 1 Public Supply", "Bedrock: Type 2 Public Supply", "Bedrock: Type 3 Public Supply",
                                                "Bedrock: All Other Wells",
                                                "Unknown Aquifer: Type 1 Public Supply",
                                                "Unknown Aquifer: Type 2 Public Supply", "Unknown Aquifer: Type 3 Public Supply",
                                                "Unknown Aquifer: All Other Wells"]})
    lyrWW.symbology = symWW
    symWW.renderer.addValues({"Aquifer Type: Well Usage": symWW.renderer.listMissingValues()[0].items})
    lyrWW.symbology = symWW
    for group in symWW.renderer.groups:
        for item in group.items:
            if item.values[0][0] == "Drift: Type 1 Public Supply":
                item.symbol.applySymbolFromGallery('Star 3')
                item.symbol.color = {'RGB': [76, 230, 0, 100]}
                item.symbol.size = 13
                lyrWW.symbology = symWW
            elif item.values[0][0] == "Drift: Type 2 Public Supply":
                item.symbol.applySymbolFromGallery('Diamond 4')
                item.symbol.color = {'RGB': [76, 230, 0, 100]}
                item.symbol.outlineWidth = 1
                item.symbol.size = 13
                lyrWW.symbology = symWW
            elif item.values[0][0] == "Drift: Type 3 Public Supply":
                item.symbol.applySymbolFromGallery('Triangle 3')
                item.symbol.color = {'RGB': [76, 230, 0, 100]}
                item.symbol.outlineWidth = 1
                item.symbol.size = 8
                lyrWW.symbology = symWW
            elif item.values[0][0] == "Drift: All Other Wells":
                item.symbol.color = {'RGB': [76, 230, 0, 100]}
                item.symbol.size = 3
                item.symbol.outlineWidth = 0
                lyrWW.symbology = symWW
            elif item.values[0][0] == "Bedrock: Type 1 Public Supply":
                item.symbol.applySymbolFromGallery('Star 3')
                item.symbol.color = {'RGB': [230, 0, 0, 100]}
                item.symbol.size = 13
                lyrWW.symbology = symWW
            elif item.values[0][0] == "Bedrock: Type 2 Public Supply":
                item.symbol.applySymbolFromGallery('Diamond 4')
                item.symbol.outlineWidth = 1
                item.symbol.size = 13
                item.symbol.color = {'RGB': [230, 0, 0, 100]}
                lyrWW.symbology = symWW
            elif item.values[0][0] == "Bedrock: Type 3 Public Supply":
                item.symbol.applySymbolFromGallery('Triangle 3')
                item.symbol.outlineWidth = 1
                item.symbol.size = 8
                item.symbol.color = {'RGB': [230, 0, 0, 100]}
                lyrWW.symbology = symWW
            elif item.values[0][0] == "Bedrock: All Other Wells":
                item.symbol.color = {'RGB': [230, 0, 0, 100]}
                item.symbol.size = 3
                item.symbol.outlineWidth = 0
                lyrWW.symbology = symWW
            if item.values[0][0] == "Unknown Aquifer: Type 1 Public Supply":
                item.symbol.applySymbolFromGallery('Star 3')
                item.symbol.color = {'RGB': [115, 178, 255, 100]}
                item.symbol.size = 13
                lyrWW.symbology = symWW
            elif item.values[0][0] == "Unknown Aquifer: Type 2 Public Supply":
                item.symbol.applySymbolFromGallery('Diamond 4')
                item.symbol.color = {'RGB': [115, 178, 255, 100]}
                item.symbol.outlineWidth = 1
                item.symbol.size = 13
                lyrWW.symbology = symWW
            elif item.values[0][0] == "Unknown Aquifer: Type 3 Public Supply":
                item.symbol.applySymbolFromGallery('Triangle 3')
                item.symbol.color = {'RGB': [115, 178, 255, 100]}
                item.symbol.outlineWidth = 1
                item.symbol.size = 8
                lyrWW.symbology = symWW
            elif item.values[0][0] == "Unknown Aquifer: All Other Wells":
                item.symbol.color = {'RGB': [115, 178, 255, 100]}
                item.symbol.size = 3
                item.symbol.outlineWidth = 0
                lyrWW.symbology = symWW
    prj.save()
def removeBasemaps(map):
    try:
        basenameLayer = map.listLayers('World Topographic Map')[0]
        hillLayer = map.listLayers('World Hillshade')[0]
        map.removeLayer(basenameLayer)
        map.removeLayer(hillLayer)
    except:
        arcpy.AddMessage('  *Basemap already removed. Passing to next step...')
        pass
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
        pm.addDataFromPath(outraster)
        prj.save()
    arcpy.management.SelectLayerByAttribute(points,"CLEAR_SELECTION")
def createBDRKraster(points,outraster,boundary):
    if int(arcpy.management.GetCount(points)[0]) < 10:
        arcpy.AddMessage("  *Not enough datapoints for the given time period. (At least 10 needed) Skipping bedrock surface...*")
        pass
    else:
        with arcpy.EnvManager(mask=boundary):
            out_raster = arcpy.sa.Idw(
                in_point_features=points,
                z_field="BDRK_ELEV",
                cell_size=10,
                power=2,
                search_radius="VARIABLE 12",
                in_barrier_polyline_features=None)
        out_raster.save(outraster)
        pm.addDataFromPath(outraster)
        prj.save()
    arcpy.management.SelectLayerByAttribute(points,"CLEAR_SELECTION")
def appendFieldMappingInput(fieldMappings,oldTable,oldField,newField,newFieldType):
    # Add the input field for the given field name
    fieldMap = arcpy.FieldMap()
    fieldMap.addInputField(oldTable,oldField)
    name = fieldMap.outputField
    name.name,name.aliasName,name.type = newField,newField,newFieldType
    fieldMap.outputField = name
    # Add output field to field mapping objects
    fieldMappings.addFieldMap(fieldMap)
# Parameters
# *******************************************************
# Name for the project to be used in the file hierarchy
projectName = arcpy.GetParameterAsText(0)

# Location of the project folder. This should be defaulted to the current folder workspace.
projectLoc = arcpy.GetParameterAsText(1)

# Boolean designation if the project is for a 2-5-mile project or not
standard_OR_no = arcpy.GetParameterAsText(2)

# Location Latitude & Longitude (decimal degrees)
siteLatLong = arcpy.ValueTable(3)
siteLatLong.loadFromString(arcpy.GetParameterAsText(3))

# DEM of the surface topography
dem = arcpy.ValueTable(2)
dem.loadFromString(arcpy.GetParameterAsText(4))

# User-defined aggregation lithology table. Designed to allow for new versions of aggregation lithologies
aggTable = arcpy.GetParameterAsText(5)

# Boolean designation if the user wants to implement their own custom date range for the GWL rasters
customRange = arcpy.GetParameterAsText(6)

# List of defined date-ranges
dateRange = arcpy.ValueTable(2)
dateRange.loadFromString(arcpy.GetParameterAsText(7))

# Local Variables
# *******************************************************
wkt = 'PROJCS["NAD_1983_Hotine_Oblique_Mercator_Azimuth_Natural_Origin",GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Hotine_Oblique_Mercator_Azimuth_Natural_Origin"],PARAMETER["False_Easting",2546731.496],PARAMETER["False_Northing",-4354009.816],PARAMETER["Scale_Factor",0.9996],PARAMETER["Azimuth",337.25556],PARAMETER["Longitude_Of_Center",-86.0],PARAMETER["Latitude_Of_Center",45.30916666666666],UNIT["Meter",1.0]];-28810000 -30359300 10000;-100000 10000;-100000 10000;0.001;0.001;0.001;IsHighPrecision'
src = arcpy.SpatialReference(text=wkt)
checkExtensions()
# Environment Variables
arcpy.env.overwriteOutput = True
arcpy.env.outputCoordinateSystem = src
prj = arcpy.mp.ArcGISProject("CURRENT")
scratchDir = prj.defaultGeodatabase
arcpy.env.preserveGlobalIds = True
arcpy.env.transferGDBAttributeProperties = True
arcpy.env.transferDomains = True
arcpy.env.workspace = scratchDir
arcpy.AddMessage("Scratch Space: " + scratchDir)

# Groups to Seperate:
textGroup = ["Coarse","Fine","Medium","Fine To Coarse","Fine To Medium","Medium To Coarse","Very Coarse","Very Fine",
             "Very Fine-Coarse","Very Fine-Fine","Very Fine-Medium"]
conGroup = ["Dense","Dry","Gummy","Karst","Porous","Strips","Cemented","Very Hard","Broken","Fractured","Heaving/Quick",
            "Stringers","Swelling","Water Bearing","Weathered","Wet/Moist","Firm","Hard","Soft"]
secGroup = ["Clayey","Dolomitic","Fill","Gravely","Organic","Sandy","Silty","Stoney","W/Boulders","W/Clay","W/Coal",
            "W/Cobbles","W/Dolomite","W/Gravel","W/Gypsum","W/Limestone","W/Pyrite","W/Sand","W/Sandstone","W/Shale",
            "W/Silt","W/Stones","Wood"]
colorGroup = ["Black","Black & Gray","Black & White","Blue","Brown","Cream","Dark Gray","Gray","Gray & White","Green",
              "Light Brown","Light Gray","Orange","Pink","Red","Rust","Tan","Tan & Gray","White","Yellow"]
groupGroup = ["Alpena Ls","Amherstburg Fm","Antrim Shale","Bass Island Group","Bayport Ls","Bedford Shale","Bell Shale",
              "Berea Ss","Black River Group","Bois Blanc Fm","Burnt Bluff Group","Cabot Head Shale","Cataract Group",
              "Coldwater Shale","Detroit River Group","Dresbach Ss","Dundee Ls","Eau Claire Member","Ellsworth Shale",
              "Engadine Dol","Franconia Ss","Freda Ss","Garden Island Fm","Glenwood Member","Grand Rapids Group",
              "Grand River Fm","Jacobsville Ss","Jordan Ss","Lake Superior Group","Lodi Member","Lucas Fm",
              "Manistique Group","Manitoulin Dol","Marshall Ss","Michigammee Fm","Michigan Fm","Mt. Simon Ss",
              "Napolean Ss","New Richmond Ss","Niagara Group","Nonesuch Shale","Oneota Dol","Parma Ss",
              "Prairie Du Chien Group","Precambrian","Queenston Shale","Red Beds","Richmond Group","Rogers City Ls",
              "Saginaw Fm","Salina Group","Shakopee Dol","Squaw Bay Ls","St. Lawrence Member","St. Peter Ss",
              "Sylvania Ss","Traverse Group","Trempealeau Fm","Trenton Group","Utica Shale"]
bdrkGroup = []
clayGroup = []
claySandGroup = []
tillGroup = []
topsoilGroup = []
sandGroup = []
gravelGroup = []
organicsGroup = []
sandFineGroup = []
sandGravelGroup = []
unkGroup = []

# We need to make sure all the terms are uploaded into a local ArcTable
localAgg = os.path.join(scratchDir,os.path.splitext(os.path.basename(aggTable))[0])
arcpy.conversion.ExcelToTable(Input_Excel_File=aggTable,
                              Output_Table=localAgg,
                              Sheet="Lithologies")
with arcpy.da.SearchCursor(localAgg,["PRIM_CONC","Final_Term"]) as cursor:
    for row in cursor:
        if row[1] == "Bedrock":
            bdrkGroup.append(row[0])
        elif row[1] == "Clay":
            clayGroup.append(row[0])
        elif row[1] == "Clay & Sand":
            claySandGroup.append(row[0])
        elif row[1] == "Diamicton":
            tillGroup.append(row[0])
        elif row[1] == "Topsoil":
            topsoilGroup.append(row[0])
        elif row[1] == "Sand":
            sandGroup.append(row[0])
        elif row[1] == "Gravel":
            gravelGroup.append(row[0])
        elif row[1] == "Organics":
            organicsGroup.append(row[0])
        elif row[1] == "Fine Sand":
            sandFineGroup.append(row[0])
        elif row[1] == "Sand & Gravel":
            sandGravelGroup.append(row[0])
        elif row[1] == "Unknown or No Record":
            unkGroup.append(row[0])
    del row
    del cursor

# Begin
# *******************************************************
### Begin creating the necessary data files for project...
# Adding in the geodatabases needed for the project with the user-given name
arcpy.AddMessage("BEGIN CREATING THE WORKSPACE WITH THE APPROPRIATE DATASETS...")
try:
    arcpy.AddMessage("Adding in the required geodatabases for the project...")
    # Create the demographic, geology, scratch, cross section, and rasters geodatabases...
    arcpy.management.CreateFileGDB(projectLoc,projectName,"CURRENT")
    demographLoc = os.path.join(projectLoc,projectName + ".gdb")
    arcpy.management.CreateFeatureDataset(demographLoc,"Demographics",src)

    geologyGDB = projectName + "_Geology"
    arcpy.management.CreateFileGDB(projectLoc,geologyGDB,"CURRENT")
    geologyLoc = os.path.join(projectLoc,geologyGDB + ".gdb")

    arcpy.management.CreateFileGDB(projectLoc,"Scratch","CURRENT")

    arcpy.management.CreateFileGDB(projectLoc,"Rasters","CURRENT")
    arcpy.management.CreateFileGDB(projectLoc,"001_CrossSectionFiles","CURRENT")

    #arcpy.conversion.TableToGeodatabase("https://services1.arcgis.com/vFQXQuqACTPxa4Yc/arcgis/rest/services/LITH_CODES_TABLE/FeatureServer/1", geologyLoc)
    #templateTable = os.path.join(geologyLoc,"L1LITH_CODES_TABLE") Not needed with the newest update
except:
    arcpy.AddError("ERROR 001: Failed to create required geodatabases")
    raise SystemError

try:
    arcpy.AddMessage("  Adding all associated domains for newly created geodatabases...")
    arcpy.management.CreateDomain(demographLoc, "DIRECTIONS", "Accepted direction orientations for cross-section lines","TEXT", "CODED")
    dircDict = {"E-W": "East - West",
               "W-E": "West - East",
               "N-S": "North - South",
               "S-N": "South - North",
               "NW-SE": "Northwest - Southeast",
               "SE-NW": "Southeast - Northwest",
               "NE-SW": "Northeast - Southwest",
               "SW-NE": "Southwest - Northeast"}
    for code in dircDict:
        arcpy.management.AddCodedValueToDomain(demographLoc, "DIRECTIONS", code, dircDict[code])
    arcpy.management.CreateDomain(demographLoc,"ROADS","Segment names for designated NFC road classifications","TEXT","CODED")
    roadDict = {"0":"Non-Certified",
                "1":"Interstate",
                "2":"Other Freeway",
                "3":"Other Principal Arterial",
                "4":"Minor Arterial",
                "5":"Major Collector",
                "6":"Minor Collector",
                "7":"NFC Local"}
    for code in roadDict:
        arcpy.management.AddCodedValueToDomain(demographLoc,"ROADS",code,roadDict[code])
    arcpy.management.CreateDomain(geologyLoc, "WellType", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    wellTDict = {"OTH": "Other",
                 "HEATP": "Heat Pump",
                 "HOSHLD": "Household",
                 "INDUS": "Industrial",
                 "IRRI": "Irrigation",
                 "TESTW": "Test Well",
                 "TY1PU": "Type I Public Supply",
                 "TY2PU": "Type II Public Supply",
                 "TY3PU": "Type III Public Supply",
                 "HEATRE": "Heat Pump: Return",
                 "HEATSU": "Heat Pump: Supply"}
    for code in wellTDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "WellType", code, wellTDict[code])
    arcpy.management.CreateDomain(geologyLoc, "Drilling", "Accepted drilling method terms from Wellogic", "TEXT",
                                  "CODED")
    drillDict = {"OTH": "Other",
                 "AUGBOR": "Auger/Bored",
                 "CABTOO": "Cable Tool",
                 "CASHAM": "Casing Hammer",
                 "DRIVEN": "Driven Hand",
                 "HOLROD": "Hollow Rod",
                 "JETTIN": "Jetted",
                 "TOOHAM": "Cable Tool w/Casing Hammer",
                 "ROTARY": "Mud Rotary",
                 "ROTHAM": "Rotary w/Casing Hammer",
                 "UNK": "Unknown"}
    for code in drillDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "Drilling", code, drillDict[code])
    arcpy.management.CreateDomain(geologyLoc, "WellAquifer", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    wAQDict = {"DRIFT": "Drift Aquifer",
               "ROCK": "Bedrock Aquifer",
               "UNK": "Unknown Aquifer",
               "DRYHOL": "Dry Hole"}
    for code in wAQDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "WellAquifer", code, wAQDict[code])
    arcpy.management.CreateDomain(demographLoc,"QGEOLOGY","Names of Quaternary surficial geology units based off of the Farrand & Bell (1987) surficial map","TEXT","CODED")
    qDict = {"W":"Water",
             "02":"Peat & Muck",
             "03":"Postglacial Alluvium",
             "04":"Dune Sand",
             "05":"Lacustrine (Clay & Silt)",
             "06":"Lacustrine (Sand & Gravel)",
             "07":"Glacial Outwash Sand and Gravel & Postglacial Alluvium",
             "08":"Ice-Contact Outwash Sand and Gravel",
             "09":"Glacial Till (Fine-Grained)",
             "10":"End Moraine (Fine-Textured Till)",
             "11":"Glacial Till (Medium-Grained)",
             "12":"End Moraine (Medium-Textured Till)",
             "13":"Glacial Till (Coarse-Grained)",
             "14":"End Moraine (Coarse-Textured Till)",
             "15":"Thin to Discontinuous Glacial Till over Bedrock",
             "16":"Artificial Fill",
             "17":"Exposed Bedrock"}
    for code in qDict:
        arcpy.management.AddCodedValueToDomain(demographLoc,"QGEOLOGY",code,qDict[code])
    arcpy.management.CreateDomain(demographLoc,"GroupNames","Group names for all formations found in Michigan","TEXT","CODED")
    arcpy.management.CreateDomain(geologyLoc, "GroupNames", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    groupDict = {"AGR": "Archean Granite & Gneissic",
                 "ANT": "Antrim Shale",
                 "AUM": "Archean Ultramafic",
                 "AVS": "Archean Volcanic & Sedimentary",
                 "BAY": "Bayport Limestone",
                 "BBF": "Bois Blanc Formation",
                 "BBG": "Burnt Bluff Group",
                 "BDG": "Badwater Greenstone",
                 "BED": "Bedford Shale",
                 "BER": "Berea Sandstone & Bedford Shale",
                 "BHD": "Big Hill Dolomite",
                 "BIF": "Bijiki Iron Formation",
                 "BIG": "Bass Island Group",
                 "BLS": "Bell Shale",
                 "BRG": "Black River Group",
                 "CHC": "Copper Harbor Conglomerate",
                 "CHO": "Chocolay Group",
                 "CHS": "Cabot Head Shale",
                 "CSM": "Collingwood Shale Member",
                 "CWT": "Coldwater Shale",
                 "DCF": "Dunn Creek Formation",
                 "DDL": "Dundee Limestone",
                 "DRG": "Detroit River Group",
                 "ELL": "Ellsworth Shale",
                 "ENG": "Engadine Group",
                 "EVC": "Emperor Volcanic Complex",
                 "FSS": "Freda Sandstone",
                 "GDQ": "Goodrich Quartzite",
                 "GIF": "Garden Island Formation",
                 "GLA": "Glacial Drift",
                 "GRF": "Grand River Formation",
                 "HEM": "Hemlock Formation",
                 "IIF": "Ironwood Iron Formation",
                 "INT": "Intrusive",
                 "JAC": "Jacobsville Sandstone",
                 "MAC": "Mackinac Breccia",
                 "MAR": "Marshall Formation",
                 "MCG": "Menominee & Chocolay Groups",
                 "MGF": "Michigamme Formation",
                 "MIF": "Michigan Formation",
                 "MND": "Manitoulin Dolomite",
                 "MQG": "Manistique Group",
                 "MUN": "Munising Formation",
                 "NIF": "Negaunee Iron Formation",
                 "NSF": "Nonesuch Formation",
                 "OBF": "Oak Bluff Formation",
                 "PAC": "Point Aux Chenes Shale",
                 "PAF": "Palms Formation",
                 "PDC": "Prairie Du Chien Group",
                 "PLV": "Portage Lake Volcanics",
                 "PRG": "Paint River Group",
                 "QUF": "Quinnesec Formation",
                 "QUS": "Queenston Shale",
                 "RAD": "Randville Dolomite",
                 "RBD": "Jurassic Red Beds",
                 "RIF": "Riverton Iron Formation",
                 "SAG": "Saginaw Formation",
                 "SAL": "Salina Group",
                 "SAQ": "Siamo Slate & Ajibik Quartzite",
                 "SCF": "Siemens Creek Formation",
                 "SID": "Saint Ignace Dolomite",
                 "SSS": "Sylvania Sandstone",
                 "STF": "Stonington Formation",
                 "SUN": "Sunbury Shale",
                 "TMP": "Trempealeau Formation",
                 "TRG": "Traverse Group",
                 "TRN": "Trenton Group",
                 "USM": "Utica Shale Member",
                 "PSS": "Parma Sandstone",
                 "GRG": "Grand Rapids Group",
                 "NSS": "Napolean Sandstone",
                 "SBL": "Squaw Bay Limestone",
                 "ALL": "Alpena Limestone",
                 "AMF": "Amherstburg Formation",
                 "LUF": "Lucas Formation",
                 "RCL": "Rogers City Limestone",
                 "NIA": "Niagara Group",
                 "CAG": "Cataract Group",
                 "RIG": "Richmond Group",
                 "GLM": "Glenwood Member",
                 "JSS": "Jordan Sandstone",
                 "SPS": "Saint Peter Sandstone",
                 "LOD": "Lodi Member",
                 "NRS": "New Richard Sandstone",
                 "OND": "Oneota Dolomite",
                 "SHD": "Shakopee Dolomite",
                 "SLM": "Saint Lawrence Member",
                 "DSS": "Dresbach Sandstone",
                 "ECM": "Eau Claire Member",
                 "FRS": "Franconia Sandstone",
                 "LSG": "Lake Superior Group",
                 "MSS": "Mount Simon Sandstone",
                 "PRE": "Precambrian Bedrock (Undefined)",
                 "UNK": "Unknown Group",
                 "AMA": "Amasa Formation"}
    for code in groupDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "GroupNames", code, groupDict[code])
        arcpy.management.AddCodedValueToDomain(demographLoc, "GroupNames", code, groupDict[code])
    arcpy.management.CreateDomain(geologyLoc, "FirstBDRK",
                                  "Definition if the unit is the first true bedrock unit in a borehole", "TEXT",
                                  "CODED")
    bdrkDict = {"YES": "Yes",
                "NO": "No",
                "NA": "Not Applicable"}
    for code in bdrkDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "FirstBDRK", code, bdrkDict[code])
    arcpy.management.CreateDomain(geologyLoc, "Color", "Accepted color terms from Wellogic", "TEXT", "CODED")
    colorDict = {"BLACK": "Black",
                 "BLACK & GRAY": "Black & Gray",
                 "BLUE": "Blue",
                 "BROWN": "Brown",
                 "CREAM": "Cream",
                 "GRAY": "Gray",
                 "GREEN": "Green",
                 "ORANGE": "Orange",
                 "PINK": "Pink",
                 "RED": "Red",
                 "RUST": "Rust",
                 "TAN": "Tan",
                 "WHITE": "White",
                 "BLACK & WHITE": "Black & White",
                 "DARK GRAY": "Dark Gray",
                 "GRAY & WHITE": "Gray & White",
                 "LIGHT BROWN": "Light Brown",
                 "LIGHT GRAY": "Light Gray",
                 "TAN & GRAY": "Tan & Gray",
                 "YELLOW": "Yellow"}
    for code in colorDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "Color", code, colorDict[code])
    arcpy.management.CreateDomain(geologyLoc, "Consistency", "Accepted consistency terms from Wellogic", "TEXT",
                                  "CODED")
    consiDict = {"DENSE": "Dense",
                 "DRY": "Dry",
                 "GUMMY": "Gummy",
                 "KARST": "Karst",
                 "POROUS": "Porous",
                 "STRIPS": "Strips",
                 "CEMENTED": "Cemented",
                 "VERY HARD": "Very Hard",
                 "BROKEN": "Broken",
                 "FRACTURED": "Fractured",
                 "HEAVING/QUICK": "Heaving/Quick",
                 "STRINGERS": "Stringers",
                 "SWELLING": "Swelling",
                 "WATER BEARING": "Water Bearing",
                 "WEATHERED": "Weathered",
                 "WET/MOIST": "Wet/Moist",
                 "FIRM": "Firm",
                 "HARD": "Hard",
                 "SOFT": "Soft"}
    for code in consiDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "Consistency", code, consiDict[code])
    arcpy.management.CreateDomain(geologyLoc, "LithAgg", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    aggDict = {"UNK": "Unknown or No Record",
               "BDRK": "Bedrock",
               "CLAY": "Clay",
               "CLSA": "Clay & Sand",
               "DIAM": "Diamicton",
               "TOPS": "Topsoil",
               "GRAV": "Gravel",
               "FSAN": "Fine Sand",
               "ORGA": "Organics",
               "SAND": "Sand",
               "SAGR": "Sand & Gravel"}
    for code in aggDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "LithAgg", code, aggDict[code])
    arcpy.management.CreateDomain(geologyLoc, "LithAquifer", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    lAQDict = {"D-AQ": "Drift: Aquifer Material",
               "D-MAQ": "Drift: Marginal Aquifer Material",
               "D-CM": "Drift: Confining Material",
               "D-PCM": "Drift: Partially Confining Material",
               "R-AQ": "Bedrock: Aquifer Material",
               "R-MAQ": "Bedrock: Marginal Aquifer Material",
               "R-CM": "Bedrock: Confining Material",
               "R-PCM": "Bedrock: Partially Confining Material",
               "D-NA": "Drift: Unknown Material",
               "R-NA": "Bedrock: Unknown Material",
               "U-NA": "Unknown: Unknown Material"}
    for code in lAQDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "LithAquifer", code, lAQDict[code])
    arcpy.management.CreateDomain(geologyLoc, "PrimaryLith", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    primDict = {"BASALT": "Basalt",
                "BOULDERS": "Boulders",
                "CLAY": "Clay",
                "CLAY & BOULDERS": "Clay & Boulders",
                "CLAY & COBBLES": "Clay & Cobbles",
                "CLAY & GRAVEL": "Clay & Gravel",
                "CLAY & SAND": "Clay & Sand",
                "CLAY & SILT": "Clay & Silt",
                "CLAY & STONES": "Clay & Stones",
                "CLAY GRAVEL SAND": "Clay Gravel Sand",
                "CLAY GRAVEL SILT": "Clay Gravel Silt",
                "CLAY GRAVEL STONES": "Clay Gravel Stones",
                "CLAY SAND GRAVEL": "Clay Sand Gravel",
                "CLAY SAND SILT": "Clay Sand Silt",
                "CLAY SILT GRAVEL": "Clay Silt Gravel",
                "CLAY SILT SAND": "Clay Silt Sand",
                "COAL": "Coal",
                "COBBLES": "Cobbles",
                "CONGLOMERATE": "Conglomerate",
                "DEBRIS": "Debris",
                "DOLOMITE": "Dolomite",
                "DOLOMITE & LIMESTONE": "Dolomite & Limestone",
                "DOLOMITE & SANDSTONE": "Dolomite & Sandstone",
                "DOLOMITE & SHALE": "Dolomite & Shale",
                "DRY HOLE": "Dry Hole",
                "GRANITE": "Granite",
                "GRAVEL": "Gravel",
                "GRAVEL & BOULDERS": "Gravel & Boulders",
                "GRAVEL & CLAY": "Gravel & Clay",
                "GRAVEL & COBBLES": "Gravel & Cobbles",
                "GRAVEL & SAND": "Gravel & Sand",
                "GRAVEL & SILT": "Gravel & Silt",
                "GRAVEL & STONES": "Gravel & Stones",
                "GRAVEL CLAY SAND": "Gravel Clay Sand",
                "GRAVEL CLAY SILT": "Gravel Clay Silt",
                "GRAVEL SAND CLAY": "Gravel Sand Clay",
                "GRAVEL SAND SILT": "Gravel Sand Silt",
                "GRAVEL SILT CLAY": "Gravel Silt Clay",
                "GRAVEL SILT SAND": "Gravel Silt Sand",
                "GREENSTONE": "Greenstone",
                "GYPSUM": "Gypsum",
                "HARDPAN": "Hardpan",
                "INTERVAL NOT SAMPLED": "Interval Not Sampled",
                "IRON FORMATION": "Iron Formation",
                "LIMESTONE": "Limestone",
                "LIMESTONE & DOLOMITE": "Limestone & Dolomite",
                "LIMESTONE & SANDSTONE": "Limestone & Sandstone",
                "LIMESTONE & SHALE": "Limestone & Shale",
                "LITHOLOGY UNKNOWN": "Lithology Unknown",
                "LOAM": "Loam",
                "MARL": "Marl",
                "MUCK": "Muck",
                "MUD": "Mud",
                "NO LITHOLOGY INFORMATION": "No Lithology Information",
                "NO LOG": "No Log",
                "PEAT": "Peat",
                "QUARTZ": "Quartz",
                "QUARTZITE": "Quartzite",
                "SAND": "Sand",
                "SAND & BOULDERS": "Sand & Boulders",
                "SAND & CLAY": "Sand & Clay",
                "SAND & COBBLES": "Sand & Cobbles",
                "SAND & GRAVEL": "Sand & Gravel",
                "SAND & SILT": "Sand & Silt",
                "SAND & STONES": "Sand & Stones",
                "SAND CLAY GRAVEL": "Sand Clay Gravel",
                "SAND CLAY SILT": "Sand Clay Silt",
                "SAND GRAVEL CLAY": "Sand Gravel Clay",
                "SAND GRAVEL SILT": "Sand Gravel Silt",
                "SAND SILT CLAY": "Sand Silt Clay",
                "SAND SILT GRAVEL": "Sand Silt Gravel",
                "SANDSTONE": "Sandstone",
                "SANDSTONE & LIMESTONE": "Sandstone & Limestone",
                "SANDSTONE & SHALE": "Sandstone & Shale",
                "SCHIST": "Schist",
                "SEE COMMENTS": "See Comments",
                "SHALE": "Shale",
                "SHALE & COAL": "Shale & Coal",
                "SHALE & LIMESTONE": "Shale & Limestone",
                "SHALE & SANDSTONE": "Shale & Sandstone",
                "SHALE SANDSTONE LIMESTONE": "Shale Sandstone Limestone",
                "SILT": "Silt",
                "SILT & BOULDERS": "Silt & Boulders",
                "SILT & CLAY": "Silt & Clay",
                "SILT & COBBLES": "Silt & Cobbles",
                "SILT & GRAVEL": "Silt & Gravel",
                "SILT & SAND": "Silt & Sand",
                "SILT & STONES": "Silt & Stones",
                "SILT CLAY GRAVEL": "Silt Clay Gravel",
                "SILT CLAY SAND": "Silt Clay Sand",
                "SILT GRAVEL CLAY": "Silt Gravel Clay",
                "SILT GRAVEL SAND": "Silt Gravel Sand",
                "SILT SAND CLAY": "Silt Sand Clay",
                "SILT SAND GRAVEL": "Silt Sand Gravel",
                "SLATE": "Slate",
                "SOAPSTONE (TALC)": "Soapstone (Talc)",
                "STONES": "Stones",
                "TOPSOIL": "Topsoil",
                "UNIDENTIFIED CONSOLIDATED FM": "Unidentified Consolidated Fm",
                "UKNOWN": "Unknown",
                "VOID": "Void"}
    for code in primDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "PrimaryLith", code, primDict[code])
    arcpy.management.CreateDomain(geologyLoc, "SecondaryLith", "Group names for all formations found in Michigan",
                                  "TEXT",
                                  "CODED")
    secDict = {"CLAYEY": "Clayey",
               "DOLOMITIC": "Dolomitic",
               "FILL": "Fill",
               "GRAVELY": "Gravely",
               "ORGANIC": "Organic",
               "SANDY": "Sandy",
               "SILTY": "Silty",
               "STONEY": "Stoney",
               "W/BOULDERS": "With Boulders",
               "W/CLAY": "With Clay",
               "W/COAL": "With Coal",
               "W/COBBLES": "With Cobbles",
               "W/DOLOMITE": "With Dolomite",
               "W/GRAVEL": "With Gravel",
               "W/GYPSUM": "With Gypsum",
               "W/LIMESTONE": "With Limestone",
               "W/PYRITE": "With Pyrite",
               "W/SAND": "With Sand",
               "W/SANDSTONE": "With Sandstone",
               "W/SHALE": "With Shale",
               "W/SILT": "With Silt",
               "W/STONES": "With Stones",
               "WOOD": "Wood"}
    for code in secDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "SecondaryLith", code, secDict[code])
    arcpy.management.CreateDomain(geologyLoc, "Simplified", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    simpDict = {"UNK": "Unknown Sediment Type",
                "FINE": "Fine-Grained Sediments",
                "COARSE": "Coarse-Grained Sediments",
                "MIXED": "Mixed-Grained Sediments",
                "ORGANIC": "Organic Sediments",
                "BEDROCK": "Bedrock Unit"}
    for code in simpDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "Simplified", code, simpDict[code])
    arcpy.management.CreateDomain(geologyLoc, "WellStatus", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    statDict = {"OTH": "Other",
                "ACT": "Active",
                "INACT": "Inactive",
                "PLU": "Plugged/Abandoned",
                "UNK": "Unknown"}
    for code in statDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "WellStatus", code, statDict[code])
    arcpy.management.CreateDomain(geologyLoc, "TestMethod", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    testDict = {"UNK": "Unknown",
                "OTH": "Other",
                "AIR": "Air",
                "BAIL": "Bailer",
                "PLUGR": "Plunger",
                "TSTPUM": "Test Pump"}
    for code in testDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "TestMethod", code, testDict[code])
    arcpy.management.CreateDomain(geologyLoc, "Texture", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    textDict = {"COARSE": "Coarse",
                "FINE": "Fine",
                "MEDIUM": "Medium",
                "FINE TO COARSE": "Fine To Coarse",
                "FINE TO MEDIUM": "Fine To Medium",
                "MEDIUM TO COARSE": "Medium To Coarse",
                "VERY COARSE": "Very Coarse",
                "VERY FINE": "Very Fine",
                "VERY FINE-COARSE": "Very Fine To Coarse",
                "VERY FINE-FINE": "Very Fine to Fine",
                "VERY FINE-MEDIUM": "Very Fine To Medium"}
    for code in textDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "Texture", code, textDict[code])
    arcpy.management.CreateDomain(geologyLoc, "Verification", "Group names for all formations found in Michigan",
                                  "TEXT",
                                  "CODED")
    verDict = {"Y": "Yes",
               "N": "No"}
    for code in verDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "Verification", code, verDict[code])
    arcpy.management.CreateDomain(geologyLoc, "Age", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    ageDict = {"UNK": "Unknown Age",
               "PH-CEN-PLEI": "Pleistocene",
               "PH-MES-MJUR": "Middle Jurassic",
               "PH-PAL-LPEN": "Late Pennsylvanian",
               "PH-PAL-EPEN": "Early Pennsylvanian",
               "PH-PAL-EPLM": "Early Pennsylvanian to Late Mississippian",
               "PH-PAL-LMIS": "Late Mississippian",
               "PH-PAL-EMIS": "Late Mississippian",
               "PH-PAL-LDEV": "Late Devonian",
               "PH-PAL-MDLD": "Late to Middle Devonian",
               "PH-PAL-MDEV": "Middle Devonian",
               "PH-PAL-EDEV": "Early Devonian",
               "PH-PAL-LSIL": "Late Silurian",
               "PH-PAL-MSIL": "Middle Silurian",
               "PH-PAL-ESIL": "Early Silurian",
               "PH-PAL-LORD": "Late Ordovician",
               "PH-PAL-MORD": "Middle Ordovician",
               "PH-PAL-EORD": "Early Ordovician",
               "PH-PAL-LCAM": "Late Cambrian",
               "PC-PRO-EARL": "Early Proterozoic",
               "PC-PRO-MIDL": "Middle Proterozoic",
               "PC": "Precambrian Age",
               "PC-ARC-EARL": "Early Archean",
               "PC-ARC-LATE": "Late Archean",
               "PC-PRO-MESO": "Mesoproterozoic",
               "PH-PAL-MDLS": "Middle Devonian to Late Silurian"}
    for code in ageDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "Age", code, ageDict[code])
    arcpy.management.CreateDomain(geologyLoc, "CasingType", "Group names for all formations found in Michigan", "TEXT",
                                  "CODED")
    caseDict = {"OTH": "Other",
                "UNK": "Unknown",
                "PVCPLA": "PVC Plastic",
                "STEBLA": "Steel: Black",
                "STEGAL": "Steel: Galvanized",
                "STEUNK": "Steel: Unknown",
                "NONE": "No Casing"}
    for code in caseDict:
        arcpy.management.AddCodedValueToDomain(geologyLoc, "CasingType", code, caseDict[code])
except:
    arcpy.AddError("ERROR 002: Failed to create and add domains to geodatabases")
    raise SystemError

try:
    arcpy.AddMessage("Adding in the required folders for the project...")
    # Creating the scratch folder
    arcpy.management.CreateFolder(projectLoc, "Scratch")
    # Creating the documents folder for PDFs and finished maps
    arcpy.management.CreateFolder(projectLoc, "PDF_Documents")
    # Creating the water wells folder
    arcpy.management.CreateFolder(projectLoc, "WaterWells")
    # Creating the StateWide_Files folder and add newest data for StateWide_Files folder
    arcpy.management.CreateFolder(projectLoc, "StateWide_Files")
    statewideLoc = os.path.join(projectLoc, "StateWide_Files")
except:
    arcpy.AddError("ERROR 003: Failed to create folders")
    raise SystemError

try:
    arcpy.AddMessage("  Adding shapefile data for StateWide_Files from Open GIS Data (SOM)...")
    onlineSchools = "https://gisagocss.state.mi.us/arcgis/rest/services/CSS/CSS_MiSTEM/MapServer/4"
    onlineColleges = "https://gisagocss.state.mi.us/arcgis/rest/services/CSS/CSS_MiSTEM/MapServer/0"
    onlineTownships = "https://gisagocss.state.mi.us/arcgis/rest/services/OpenData/michigan_geographic_framework/MapServer/2"
    onlinePLSS = "https://gisagocss.state.mi.us/arcgis/rest/services/OpenData/boundaries/MapServer/4"
    onlineCounties = "https://gisagocss.state.mi.us/arcgis/rest/services/OpenData/michigan_geographic_framework/MapServer/0"
    onlineBedrock = "https://gisagocss.state.mi.us/arcgis/rest/services/OpenData/geology/MapServer/0"
    onlineQuaternary = "https://gisagocss.state.mi.us/arcgis/rest/services/OpenData/geology/MapServer/5"
    onlineLakes = "https://gisagocss.state.mi.us/arcgis/rest/services/OpenData/hydro/MapServer/23"
    onlineRivers = "https://gisagocss.state.mi.us/arcgis/rest/services/OpenData/hydro/MapServer/2"
    onlineRoads = "https://gisagocss.state.mi.us/arcgis/rest/services/OpenData/michigan_geographic_framework/MapServer/20"
    onlineRailroads = "https://gisagocss.state.mi.us/arcgis/rest/services/OpenData/michigan_geographic_framework/MapServer/9"
    # Schools...
    arcpy.AddMessage("  Downloading statewide datasets...")
    arcpy.conversion.FeatureClassToFeatureClass(onlineSchools,statewideLoc, "Schools.shp", '','','')
    # Colleges...
    arcpy.conversion.FeatureClassToFeatureClass(onlineColleges, statewideLoc, "Colleges.shp", '', '', '')
    # Townships...
    arcpy.conversion.FeatureClassToFeatureClass(onlineTownships, statewideLoc, "Townships.shp", '', '', '')
    # PLSS Sections...
    arcpy.conversion.FeatureClassToFeatureClass(onlinePLSS, statewideLoc, "PLSS_Sections.shp", '', '', '')
    # Counties...
    arcpy.conversion.FeatureClassToFeatureClass(onlineCounties, statewideLoc, "Counties.shp", '', '', '')
    # Bedrock Geology Polygons...
    arcpy.conversion.FeatureClassToFeatureClass(onlineBedrock, statewideLoc, "Bedrock_Geology.shp", '', '', '')
    # Quaternary Geology Polygons...
    arcpy.conversion.FeatureClassToFeatureClass(onlineQuaternary, statewideLoc, "Quaternary Geology Map.shp", '', '', '')
    # Lakes...
    arcpy.conversion.FeatureClassToFeatureClass(onlineLakes, statewideLoc, "Lakes.shp", '', '', '')
    # Railroads...
    arcpy.conversion.FeatureClassToFeatureClass(onlineRailroads, statewideLoc, "Railroads.shp", '', '', '')
except:
    arcpy.AddError("ERROR 004: Failed to download and copy shapefile data")
    raise SystemError

try:
    arcpy.management.CreateFeatureclass(demographLoc, "Location", "POINT", None, "DISABLED", "DISABLED",
                                        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]];-400 -400 1111948722.22222;-100000 10000;-100000 10000;8.98315284119521E-09;0.001;0.001;IsHighPrecision',
                                        '', 0, 0, 0, '')
    outLocation = os.path.join(demographLoc, "Location")
    arcpy.management.AddField(outLocation, "NAME", "TEXT", "", "", "1000", "", "NULLABLE", "NON_REQUIRED", "")
    for i in range(0,siteLatLong.rowCount):
        siteName = siteLatLong.getValue(i,0)
        siteLat = siteLatLong.getValue(i,1)
        siteLong = siteLatLong.getValue(i,2)

        arcpy.AddMessage("Creating the location feature class at the given coordinates ({}, {})...".format(siteLat, siteLong))

        #Defining the location data for the site
        siteCoords = [siteLong, siteLat]
        x = siteCoords[0]
        y = siteCoords[1]
        point_obj = arcpy.Point(x,y)
        point_obj.X = x
        point_obj.Y = y
        row = [siteName, point_obj]
        with arcpy.da.InsertCursor(outLocation, ["NAME", "SHAPE@"]) as cursor:
            cursor.insertRow(row)
            del cursor
    siteLoc = os.path.join(demographLoc, "POI_Location")
    arcpy.management.Project(outLocation, siteLoc, src, "WGS_1984_(ITRF00)_To_NAD_1983", 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]', "NO_PRESERVE_SHAPE", None, "NO_VERTICAL")
except:
    arcpy.AddError("ERROR 005: Failed to create location feature class")
    raise SystemError

try:
    arcpy.AddMessage("Creating the cross-section feature class...")
    arcpy.management.CreateFeatureclass(demographLoc, "XSEC_Lines", "POLYLINE", None, "DISABLED", "DISABLED", src)
    #Add the appropriate fields for the name and the direction
    outXSEC = os.path.join(demographLoc, "XSEC_Lines")
    arcpy.management.AddField(outXSEC, "XSEC", "TEXT", "", "", "255", "", "NULLABLE", "NON_REQUIRED", "")
    arcpy.management.AddField(outXSEC, "DIRECTION", "TEXT", "", "", "255", "", "NULLABLE", "NON_REQUIRED", "")
    #Adding the domain signature for the DIRECTION field
    arcpy.management.AssignDomainToField(outXSEC, "DIRECTION", "DIRECTIONS")
except:
    arcpy.AddError("ERROR 006: Failed to create cross-section line feature class")
    raise SystemError

try:
    arcpy.AddMessage("Determining if multiple rasters are given...")
    locRaster = os.path.join(projectLoc, "Rasters.gdb")
    RASTERNAME = projectName + "_DEM_ft_FULLEXTENT"
    fullDEM = os.path.join(locRaster,RASTERNAME)
    if 1 < dem.rowCount:
        arcpy.AddMessage("- Mosaic DEM surface(s)")
        for i in range(0,dem.rowCount):
            demRaster = dem.getValue(i,0)
            elevUnits = dem.getValue(i,1)
            if elevUnits == "Meters":
                demFeet = os.path.join(scratchDir, os.path.splitext(os.path.basename(demRaster))[0] + "_feet")
                output_raster = arcpy.Raster(demRaster)/0.3048
                output_raster.save(demFeet)
            if elevUnits == "Feet":
                demFeet = os.path.join(scratchDir, os.path.splitext(os.path.basename(demRaster))[0] + "_feet")
                arcpy.management.CopyRaster(demRaster, demFeet)
        areaDEM = projectName + "_ProjectArea"
        demList = arcpy.ListRasters()
        mosListDem = ";".join(demList)
        arcpy.management.MosaicToNewRaster(mosListDem, locRaster, areaDEM, src, "32_BIT_FLOAT", None, 1, "LAST","FIRST")
        mosDEM = os.path.join(locRaster, areaDEM)
        arcpy.management.CopyRaster(mosDEM, fullDEM)
        arcpy.management.Delete(mosDEM)
    else:
        arcpy.AddMessage("- One raster given. Copying current DEM...")
        for i in range(0,dem.rowCount):
            demRaster = dem.getValue(i,0)
            elevUnits = dem.getValue(i,1)
            if elevUnits == "Meters":
                demFeet = os.path.join(scratchDir, os.path.splitext(os.path.basename(demRaster))[0] + "_feet")
                output_raster = arcpy.Raster(demRaster) / 0.3048
                output_raster.save(demFeet)
                arcpy.management.CopyRaster(demFeet, fullDEM)
                arcpy.management.Delete(demFeet)
            if elevUnits == "Feet":
                arcpy.management.CopyRaster(demRaster, fullDEM)
except:
    arcpy.AddError("ERROR 007: Failed to mosaic rasters together.")
    raise SystemError

try:
    arcpy.AddMessage("Creating the boundary(s)...")
    if standard_OR_no == "Standard 2-5 Mile Project":
        buff2mile = os.path.join(demographLoc, "BuffZone_2mile")
        arcpy.analysis.Buffer(in_features=siteLoc,
                              out_feature_class=buff2mile,
                              buffer_distance_or_field="2 Miles",
                              dissolve_option="ALL")
        buff5mile = os.path.join(demographLoc, "BuffZone_5mile")
        arcpy.analysis.Buffer(in_features=siteLoc,
                              out_feature_class=buff5mile,
                              buffer_distance_or_field="5 Miles",
                              dissolve_option="ALL")
    if standard_OR_no == "Non-Standard Project Area":
        featExtent = os.path.join(scratchDir, "DEM_Extent")
        arcpy.ddd.RasterDomain(fullDEM,featExtent,"POLYGON")
        #demDesc = arcpy.Describe(fullDEM)
        #coordinates = [(demDesc.extent.XMax,demDesc.extent.YMax),
        #               (demDesc.extent.XMax,demDesc.extent.YMin),
        #               (demDesc.extent.XMin,demDesc.extent.YMin),
        #               (demDesc.extent.XMin,demDesc.extent.YMax)]
        #results = arcpy.management.CreateFeatureclass(scratchDir,"DEM_Extent","POLYGON","","","",src)
        #featExtent = results[0]
        #with arcpy.da.InsertCursor(featExtent,["SHAPE@"]) as cursor:
        #    cursor.insertRow([coordinates])
        #    del cursor
        buff2mile = os.path.join(demographLoc, "BuffZone_2mile")
        arcpy.analysis.Buffer(in_features=siteLoc,
                              out_feature_class=buff2mile,
                              buffer_distance_or_field="2 Miles",
                              dissolve_option="ALL")
except:
    arcpy.AddError("ERROR 008: Failed to create boundary")
    raise SystemError

try:
    arcpy.AddMessage("Creating project topographic raster...")
    prjDEM = os.path.join(locRaster,projectName+"_DEM_ft")
    if standard_OR_no == "Standard 2-5 Mile Project":
        extractRast = arcpy.sa.ExtractByMask(fullDEM, buff5mile)
        extractRast.save(prjDEM)
    if standard_OR_no == "Non-Standard Project Area":
        arcpy.management.CopyRaster(fullDEM,prjDEM)
    arcpy.AddMessage("  Creating hillshade of {}...".format(os.path.splitext(os.path.basename(prjDEM))[0]))
    hillName = os.path.join(locRaster,"HILLSHADE")
    arcpy.ddd.HillShade(prjDEM,hillName,315,45,"NO_SHADOWS",1)
except:
    arcpy.AddError("ERROR 009: Failed to extract and create hillshade of {}".format(os.path.splitext(os.path.basename(prjDEM))[0]))
    raise SystemError

try:
    arcpy.AddMessage("  Creating 10 feet contours of {}...".format(os.path.splitext(os.path.basename(prjDEM))[0]))
    contourLines = os.path.join(locRaster,projectName + "_10ft_contours")
    arcpy.sa.Contour(prjDEM,contourLines,10)
    arcpy.management.AddField(contourLines,"CONTOUR_TYPE","TEXT","","","255","","NULLABLE","NON_REQUIRED","")
    with arcpy.da.UpdateCursor(contourLines,["Contour","CONTOUR_TYPE"]) as cursor:
        for row in cursor:
            if float(row[0]/50).is_integer():
                row[1] = "INDEX"
            else:
                row[1] = "INTERMEDIATE"
            cursor.updateRow(row)
        del row,cursor
    arcpy.AddMessage("  Creating 20 feet contours of {}...".format(os.path.splitext(os.path.basename(prjDEM))[0]))
    contourLines20 = os.path.join(locRaster,projectName + "_20ft_contours")
    arcpy.sa.Contour(prjDEM,contourLines20,20)
    arcpy.management.AddField(contourLines20, "CONTOUR_TYPE", "TEXT", "", "", "255", "", "NULLABLE", "NON_REQUIRED", "")
    with arcpy.da.UpdateCursor(contourLines20, ["Contour", "CONTOUR_TYPE"]) as cursor:
        for row in cursor:
            if float(row[0] / 100).is_integer():
                row[1] = "INDEX"
            else:
                row[1] = "INTERMEDIATE"
            cursor.updateRow(row)
        del row, cursor
except:
    arcpy.AddError("ERROR 010: Failed to create contour lines for {}".format(os.path.splitext(os.path.basename(prjDEM))[0]))
    raise SystemError

try:
    arcpy.AddMessage("Clipping down features from StateWide_Files folder...")
    demoLoc = os.path.join(demographLoc, "Demographics")

    # Analyzing the roads features
    roadsname = projectName + "_Roads"
    roadsFeat = os.path.join(demoLoc, roadsname)
    if standard_OR_no == "Standard 2-5 Mile Project":
        arcpy.analysis.Clip(onlineRoads, buff5mile, roadsFeat, "")
    if standard_OR_no == "Non-Standard Project Area":
        arcpy.analysis.Clip(onlineRoads, featExtent, roadsFeat, "")
    #arcpy.management.AssignDomainToField(roadsFeat, "NFC", "ROADS")

    # Analyzing the lakes features
    lakesShape = os.path.join(statewideLoc, "Lakes.shp")
    lakesname = projectName + "_Lakes"
    lakesFeat = os.path.join(demoLoc, lakesname)
    if standard_OR_no == "Standard 2-5 Mile Project":
        arcpy.analysis.Clip(lakesShape, buff5mile, lakesFeat, "")
    if standard_OR_no == "Non-Standard Project Area":
        arcpy.analysis.Clip(lakesShape, featExtent, lakesFeat, "")

    #Analyzing the rivers features
    riversShape = os.path.join(statewideLoc, "Rivers.shp")
    riversname = projectName + "_Rivers"
    riversFeat = os.path.join(demoLoc, riversname)
    if standard_OR_no == "Standard 2-5 Mile Project":
        arcpy.analysis.Clip(onlineRivers, buff5mile, riversFeat, "")
    if standard_OR_no == "Non-Standard Project Area":
        arcpy.analysis.Clip(onlineRivers, featExtent, riversFeat, "")

    # Analyzing the schools features
    schoolsShape = os.path.join(statewideLoc, "Schools.shp")
    schoolsname = projectName + "_Schools"
    schoolsFeat = os.path.join(demoLoc, schoolsname)
    if standard_OR_no == "Standard 2-5 Mile Project":
        arcpy.analysis.Clip(schoolsShape, buff5mile, schoolsFeat, "")
    if standard_OR_no == "Non-Standard Project Area":
        arcpy.analysis.Clip(schoolsShape, featExtent, schoolsFeat, "")

    #Analyzing the surface Quaternary geology features
    geologyShape = os.path.join(statewideLoc, "Quaternary Geology Map.shp")
    geologyname = projectName + "_QGeology"
    geologyFeat = os.path.join(demoLoc, geologyname)
    if standard_OR_no == "Standard 2-5 Mile Project":
        arcpy.analysis.Clip(geologyShape, buff5mile, geologyFeat, "")
    if standard_OR_no == "Non-Standard Project Area":
        arcpy.analysis.Clip(geologyShape, featExtent, geologyFeat, "")
    arcpy.management.AssignDomainToField(geologyFeat, "TEXT_CODE", "QGEOLOGY")

    #Analyzing the bedrock geology features
    BDRKShape = os.path.join(statewideLoc, "Bedrock_Geology.shp")
    BDRKname = projectName + "_BDRKGeology"
    BDRKFeat = os.path.join(demoLoc, BDRKname)
    if standard_OR_no == "Standard 2-5 Mile Project":
        arcpy.analysis.Clip(BDRKShape, buff5mile, BDRKFeat, "")
    if standard_OR_no == "Non-Standard Project Area":
        arcpy.analysis.Clip(BDRKShape, featExtent, BDRKFeat, "")
    arcpy.management.AssignDomainToField(BDRKFeat, "TEXT_CODE", "GroupNames")

    # Analyzing the college features
    collegeShape = os.path.join(statewideLoc, "Colleges.shp")
    College_name = projectName + "_Colleges"
    collegeFeat = os.path.join(demoLoc, College_name)
    if standard_OR_no == "Standard 2-5 Mile Project":
        arcpy.analysis.Clip(collegeShape, buff5mile, collegeFeat, "")
    if standard_OR_no == "Non-Standard Project Area":
        arcpy.analysis.Clip(collegeShape, featExtent, collegeFeat, "")

    # Analyzing the railroad features
    railShape = os.path.join(statewideLoc, "Railroads.shp")
    railName = projectName + "_Railroads"
    railFeat = os.path.join(demoLoc, railName)
    if standard_OR_no == "Standard 2-5 Mile Project":
        arcpy.analysis.Clip(railShape, buff5mile, railFeat, "")
    if standard_OR_no == "Non-Standard Project Area":
        arcpy.analysis.Clip(railShape, featExtent, railFeat, "")
except:
    arcpy.AddError("ERROR 011: Failed to clip the necessary shapefiles into area features")
    raise SystemError

try:
    arcpy.AddMessage("Selecting and exporting features in StateWide_Files folder where clipping is not appropriate...")
    # Selcting the county(s) that will need to be included in the analysis
    countyShape = os.path.join(statewideLoc, "Counties.shp")
    if standard_OR_no == "Standard 2-5 Mile Project":
        selectCounty = arcpy.management.SelectLayerByLocation(countyShape, "INTERSECT", buff5mile)
    if standard_OR_no == "Non-Standard Project Area":
        selectCounty = arcpy.management.SelectLayerByLocation(countyShape, "INTERSECT", featExtent)
    countyname = projectName + "_Counties"
    arcpy.conversion.FeatureClassToFeatureClass(selectCounty, demoLoc, countyname, "", "", "")

    #Selecting the townships that will need to be included in the analysis
    townShape = os.path.join(statewideLoc, "Townships.shp")
    if standard_OR_no == "Standard 2-5 Mile Project":
        selectTown = arcpy.management.SelectLayerByLocation(townShape, "INTERSECT", buff5mile)
    if standard_OR_no == "Non-Standard Project Area":
        selectTown = arcpy.management.SelectLayerByLocation(townShape, "INTERSECT", featExtent)
    townname = projectName + "_Townships"
    arcpy.conversion.FeatureClassToFeatureClass(selectTown, demoLoc, townname, "", "", "")
    selectCTowns = arcpy.management.SelectLayerByLocation(townShape, "HAVE_THEIR_CENTER_IN", os.path.join(demoLoc, countyname))
    CTowns = projectName + "_CountyTowns"
    arcpy.conversion.FeatureClassToFeatureClass(selectCTowns, demoLoc, CTowns, "", "", "")

    #Selecting the sections that will be needed in the analysis
    sectionsShape = os.path.join(statewideLoc, "PLSS_Sections.shp")
    townFeat = os.path.join(demoLoc, townname)
    selectSection = arcpy.management.SelectLayerByLocation(sectionsShape, "HAVE_THEIR_CENTER_IN", townFeat)
    sectionname = projectName + "_Sections"
    arcpy.conversion.FeatureClassToFeatureClass(selectSection, demoLoc, sectionname, "", "", "")
except:
    arcpy.AddError("ERROR 012: Failed to select and export the necessary shapefiles into area features")
    raise SystemError

try:
    arcpy.AddMessage("Downloading and extracting water well data from Wellogic...")
    wellsFolder = os.path.join(projectLoc, "WaterWells")
    countyLocation = os.path.join(demoLoc,countyname)
    countyList = []
    with arcpy.da.UpdateCursor(countyLocation, ["FIPSCODE","NAME"]) as cursor:
        for row in cursor:
            if row[0] == "055":
                row[1] = "Grand_Traverse"
            elif row[0] == "141":
                row[1] =  "Presque_Isle"
            elif row[0] == "147":
                row[1] = "St_Clair"
            elif row[0] == "149":
                row[1] = "St_Joseph"
            elif row[0] == "159":
                row[1] = "Van_Buren"
            else:
                pass
            cursor.updateRow(row)
            countyList.append(row[1])
    del row, cursor
    arcpy.AddMessage("- County(s) in the 5-mile radius of the location are: {}".format(countyList))
    for layer in countyList:
        arcpy.AddMessage("  Beginning download and extraction of {}...".format(layer))
        url = "https://www.deq.state.mi.us/gis-data/downloads/waterwells/" + layer + "_WaterWells.zip"  # Web link for zipped water well data
        req = requests.get(url)

        unzip = zipfile.ZipFile(BytesIO(req.content))

        unzip.extractall(wellsFolder)
except:
    arcpy.AddError("ERROR 013: Failed to download and extract Wellogic dataset(s)")
    raise SystemError

if len(countyList) > 1:
    try:
        arcpy.AddMessage("  - Multiple counties identified in the project area. Merging Wellogic datasets into one...")
        countyWellShapes = []
        for layer in countyList:
            shapeName = os.path.join(wellsFolder, layer + "_WaterWells.shp")
            countyWellShapes.append(shapeName)
        arcpy.management.Merge(countyWellShapes, os.path.join(wellsFolder, projectName + "_WaterWells.shp"), "", "")
        pointsShape = os.path.join(wellsFolder, projectName + "_WaterWells.shp")
        countyWellLiths = []
        for layer in countyList:
            tableName = os.path.join(wellsFolder, layer + "_lith.dbf")
            countyWellLiths.append(tableName)
        arcpy.management.Merge(countyWellLiths, os.path.join(wellsFolder, projectName + "_lith.dbf"), "", "")
        pointsTable = os.path.join(wellsFolder, projectName + "_lith.dbf")
    except:
        arcpy.AddError("ERROR 014: Failed to merge Wellogic datasets")
        raise SystemError
else:
    try:
        arcpy.AddMessage("  - One county identified in the project area. Continuing with process...")
        for layer in countyList:
            pointsShape = os.path.join(wellsFolder, layer + "_WaterWells.shp")
            pointsTable = os.path.join(wellsFolder, layer + "_lith.dbf")
        pass
    except:
        arcpy.AddError("ERROR 014: Failed to pass through merging step")
        raise SystemError
arcpy.AddMessage("***" + projectName + " FOLDERS, GEODATABASES, AND FILES HAVE BEEN CREATED AND IS READY FOR USE***")

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("BEGIN CREATING MAPS AND SYMBOLIZING FEATURES...")
try:
    # Add all the necessary map files, if they are not already created by name...
    mapList = ['02_Layout Map - Main', '03_Layout Map - Cross Section', '04_County Context', '05_State Context']
    for m in mapList:
        if m in prj.listMaps():
            pass
        else:
            prj.createMap(m)
except:
    arcpy.AddError("ERROR 015: Failed to create the new maps")
    raise SystemError

try:
    # Add in all the necessary datasets in the processing map...
    pm = prj.activeMap
    if standard_OR_no == "Standard 2-5 Mile Project":
        pmLayers = [hillName, prjDEM, contourLines, lakesFeat, riversFeat, roadsFeat, railFeat, schoolsFeat,
                    collegeFeat,
                    os.path.join(demoLoc, sectionname), os.path.join(demoLoc, townname), os.path.join(demoLoc, countyname),
                    outXSEC, buff2mile, buff5mile, siteLoc]
        for feats in pmLayers:
            pm.addDataFromPath(feats)
        extentLyr = pm.listLayers(os.path.splitext(os.path.basename(buff5mile))[0])[0]
    if standard_OR_no == "Non-Standard Project Area":
        pmLayers = [hillName, prjDEM, contourLines, lakesFeat, riversFeat, roadsFeat, railFeat, schoolsFeat,
                    collegeFeat,
                    os.path.join(demoLoc, sectionname), os.path.join(demoLoc, townname), os.path.join(demoLoc, countyname),
                    outXSEC, buff2mile,featExtent, siteLoc]
        for feats in pmLayers:
            pm.addDataFromPath(feats)
        extentLyr = pm.listLayers(os.path.splitext(os.path.basename(featExtent))[0])[0]
    removeBasemaps(map=pm)
    pm.defaultCamera.setExtent(arcpy.Describe(extentLyr).extent)
except:
    arcpy.AddError("ERROR 016: Failed to add in datasets for active map")
    raise SystemError

try:
    # Add data to each of the newly created maps...
    # State Context Map...
    sm = prj.listMaps('05_State Context')[0]
    smLayers = [countyShape, os.path.join(demoLoc, countyname)]
    for feats in smLayers:
        sm.addDataFromPath(feats)
    removeBasemaps(map=sm)

    # County Context Map...
    cm = prj.listMaps('04_County Context')[0]
    cmLayers = [os.path.join(demoLoc, CTowns), os.path.join(demoLoc, countyname),siteLoc]
    for feats in cmLayers:
        cm.addDataFromPath(feats)
    removeBasemaps(map=cm)

    # Main Map Layout...
    mm = prj.listMaps('02_Layout Map - Main')[0]
    if standard_OR_no == "Standard 2-5 Mile Project":
        mmLayers = [hillName, prjDEM, contourLines, lakesFeat, riversFeat, roadsFeat, railFeat, schoolsFeat,
                    collegeFeat,
                    os.path.join(demoLoc, sectionname), os.path.join(demoLoc, townname), os.path.join(demoLoc, countyname),
                    outXSEC, buff2mile, buff5mile, siteLoc]
    if standard_OR_no == "Non-Standard Project Area":
        mmLayers = [hillName, prjDEM, contourLines, lakesFeat, riversFeat, roadsFeat, railFeat, schoolsFeat,
                    collegeFeat,
                    os.path.join(demoLoc, sectionname), os.path.join(demoLoc, townname), os.path.join(demoLoc, countyname),
                    outXSEC, buff2mile, featExtent, siteLoc]
    for feats in mmLayers:
        mm.addDataFromPath(feats)
    removeBasemaps(map=mm)

    # Cross-Section Map Layout...
    csm = prj.listMaps('03_Layout Map - Cross Section')[0]
    csmLayers = [hillName,prjDEM,contourLines,lakesFeat,riversFeat,roadsFeat,railFeat,buff2mile,outXSEC,siteLoc]
    for feats in csmLayers:
        csm.addDataFromPath(feats)
    removeBasemaps(map=csm)
except:
    arcpy.AddError("ERROR 017: Failed to add data to the newly created maps")
    raise SystemError

try:
    # Formatting the map features' symbology...
    # State Context...
    stateCSymbol(map=sm,
                 feature=countyname)        # string name needed for feature
    countySymbol(map=sm,
                 feature="Counties")        # string name needed for feature

    # County Context...
    townSymbol(map=cm,
               feature=CTowns)              # string name needed for feature
    countySymbol(map=cm,
                 feature=countyname)        # string name needed for feature
    locSymbol(map=cm,
              feature=siteLoc)              # os path needed for feature

    # Main Map Layout...
    DEMSymbol(map=mm,
              feature=prjDEM)               # os path needed for feature
    roadSymbol(map=mm,
               feature=roadsFeat)           # os path needed for feature
    contoursSymbol(map=mm,
                   feature=contourLines)    # os path needed for feature
    lakesSymbol(map=mm,
                feature=lakesFeat)          # os path needed for feature
    riverSymbol(map=mm,
                feature=riversFeat)         # os path needed for feature
    schoolSymbol(map=mm,
                 feature=schoolsFeat)       # os path needed for feature
    collegeSymbol(map=mm,
                  feature=collegeFeat)      # os path needed for feature
    railSymbol(map=mm,
               feature=railFeat)            # os path needed for feature
    sectionSymbol(map=mm,
                  feature=sectionname)      # string name needed for feature
    townSymbol(map=mm,
               feature=townname)            # string name needed for feature
    countySymbol(map=mm,
                 feature=countyname)        # string name needed for feature
    if standard_OR_no == "Standard 2-5 Mile Project":
        mile2Symbol(map=mm,
                    feature=buff2mile)      # os path needed for feature
        mile5Symbol(map=mm,
                    feature=buff5mile)      # os path needed for feature
    if standard_OR_no == "Non-Standard Project Area":
        mile2Symbol(map=mm,
                    feature=buff2mile)      # os path needed for feature
        extentSymbol(map=mm,
                     feature=featExtent)    # os path needed for feature
    locSymbol(map=mm,
              feature=siteLoc)              # os path needed for feature
    xsecSymbol(map=mm,
               feature=outXSEC)             # os path needed for feature

    # Cross-Section Map Layout...
    DEMSymbol(map=csm,
              feature=prjDEM)               # os path needed for feature
    contoursSymbol(map=csm,
                   feature=contourLines)    # os path needed for feature
    locSymbol(map=csm,
              feature=siteLoc)              # os path needed for feature
    riverSymbol(map=csm,
                feature=riversFeat)         # os path needed for feature
    lakesSymbol(map=csm,
                feature=lakesFeat)          # os path needed for feature
    roadSymbol(map=csm,
               feature=roadsFeat)           # os path needed for feature
    railSymbol(map=csm,
               feature=railFeat)            # os path needed for feature
    xsecSymbol(map=csm,
               feature=outXSEC)             # os path needed for feature
    mile2Symbol(map=csm,
                feature=buff2mile)          # os path needed for feature

    # Processing Map...
    DEMSymbol(map=pm,
              feature=prjDEM)               # os path needed for feature
    roadSymbol(map=pm,
               feature=roadsFeat)           # os path needed for feature
    contoursSymbol(map=pm,
                   feature=contourLines)    # os path needed for feature
    lakesSymbol(map=pm,
                feature=lakesFeat)          # os path needed for feature
    riverSymbol(map=pm,
                feature=riversFeat)         # os path needed for feature
    schoolSymbol(map=pm,
                 feature=schoolsFeat)       # os path needed for feature
    collegeSymbol(map=pm,
                  feature=collegeFeat)      # os path needed for feature
    railSymbol(map=pm,
               feature=railFeat)            # os path needed for feature
    sectionSymbol(map=pm,
                  feature=sectionname)      # string name needed for feature
    townSymbol(map=pm,
               feature=townname)            # string name needed for feature
    countySymbol(map=pm,
                 feature=countyname)        # string name needed for feature
    if standard_OR_no == "Standard 2-5 Mile Project":
        mile2Symbol(map=pm,
                    feature=buff2mile)      # os path needed for feature
        mile5Symbol(map=pm,
                    feature=buff5mile)      # os path needed for feature
    if standard_OR_no == "Non-Standard Project Area":
        mile2Symbol(map=pm,
                    feature=buff2mile)      # os path needed for feature
        extentSymbol(map=pm,
                     feature=featExtent)    # os path needed for feature
    locSymbol(map=pm,
              feature=siteLoc)              # os path needed for feature
    xsecSymbol(map=pm,
               feature=outXSEC)             # os path needed for feature
except:
    arcpy.AddError("ERROR 018: Failed to symbolize and format features in map views")
    raise SystemError

arcpy.AddMessage('_____________________________')
AddMsgAndPrint("BEGIN FORMATTING THE LITHOLOGY TABLE OF THE DOWNLOADED WATER WELLS...")
try:
    # Now we need to format the old tables and to be used in the new tables...
    AddMsgAndPrint("  Create copy of {} and create new fields...".format(os.path.splitext(os.path.basename(pointsTable))[0]))
    lithTable = os.path.join(scratchDir,
                             os.path.splitext(os.path.basename(pointsTable))[0].replace(" ", "_") + "_validation")
    arcpy.conversion.ExportTable(in_table=pointsTable, out_table=lithTable)

    # Add in all the fields we will need before transferring them to the final table...
    arcpy.management.AddField(in_table=lithTable, field_name="PRIM_CONC", field_type="TEXT", field_length=255)
    arcpy.management.AddField(in_table=lithTable, field_name="TEXTURE", field_type="TEXT", field_length=255)
    arcpy.management.AddField(in_table=lithTable, field_name="CON", field_type="TEXT", field_length=255)
    arcpy.management.AddField(in_table=lithTable, field_name="SEC_DESC", field_type="TEXT", field_length=255)
    arcpy.management.AddField(in_table=lithTable, field_name="AQ", field_type="TEXT", field_length=255)
    arcpy.management.AddField(in_table=lithTable, field_name="AGG", field_type="TEXT", field_length=255)

    # Now, let's format the fields before we begin the appending process
    arcpy.management.CalculateField(in_table=lithTable,
                                    field="AQ",
                                    expression='!AQTYPE! + "-" + !MAQTYPE!')
    codeBlock = ("""def Combo(prim,second):
        if second == " ":
            return prim + "_"
        else:
            return prim + "_" + second""")
    arcpy.management.CalculateField(in_table=lithTable,
                                    field="PRIM_CONC",
                                    expression="Combo(!PRIM_LITH!,!LITH_MOD!)",
                                    code_block=codeBlock)
    with arcpy.da.UpdateCursor(lithTable,["PRIM_CONC","AGG"]) as cursor:
        for row in cursor:
            if row[0] in bdrkGroup:
                row[1] = "BDRK"
            elif row[0] in clayGroup:
                row[1] = "CLAY"
            elif row[0] in claySandGroup:
                row[1] = "CLSA"
            elif row[0] in tillGroup:
                row[1] = "DIAM"
            elif row[0] in topsoilGroup:
                row[1] = "TOPS"
            elif row[0] in sandGroup:
                row[1] = "SAND"
            elif row[0] in gravelGroup:
                row[1] = "GRAV"
            elif row[0] in organicsGroup:
                row[1] = "ORGA"
            elif row[0] in sandFineGroup:
                row[1] = "FSAN"
            elif row[0] in sandGravelGroup:
                row[1] = "SAGR"
            elif row[0] in unkGroup:
                row[1] = "UNK"
            else:
                row[1] = "UNK"
            cursor.updateRow(row)
        del row
        del cursor
    with arcpy.da.UpdateCursor(lithTable, ["LITH_MOD","TEXTURE","CON","SEC_DESC"]) as cursor:
        for row in cursor:
            if row[0] in textGroup:
                row[1] = row[0].upper()
            elif row[0] in conGroup:
                row[2] = row[0].upper()
            elif row[0] in secGroup:
                row[3] = row[0].upper()
            else:
                pass
            cursor.updateRow(row)
        del row
        del cursor
    with arcpy.da.UpdateCursor(lithTable, "COLOR") as cursor:
        for row in cursor:
            if row[0] in colorGroup:
                row[0] = row[0].upper()
            else:
                row[0] = None
            cursor.updateRow(row)
        del row
        del cursor
except:
    AddMsgAndPrint("ERROR 019: Failed to format old table",2)
    raise SystemError
try:
    # Now let's build the new lithology table...
    newLithTable = os.path.join(geologyLoc,
                                os.path.splitext(os.path.basename(pointsTable))[0].replace(" ", "_") + "_table_FINAL")
    AddMsgAndPrint("Creating final lithology table {} and appending old data from {}...".format(
        os.path.splitext(os.path.basename(newLithTable))[0], os.path.splitext(os.path.basename(lithTable))[0]))
    arcpy.management.CreateTable(geologyLoc,
                                 os.path.splitext(os.path.basename(pointsTable))[0].replace(" ", "_") + "_table_FINAL")
    arcpy.management.AddField(in_table=newLithTable,field_name="WELLID",field_type="TEXT",field_length=12,
                              field_alias="Well ID")
    arcpy.management.AddField(in_table=newLithTable, field_name="SEQ_NUM", field_type="SHORT", field_length=12,
                              field_alias="Sequence Number")
    arcpy.management.AddField(in_table=newLithTable, field_name="DRLLR_DESC", field_type="TEXT", field_length=1000,
                              field_alias="Full Driller Description")
    arcpy.management.AddField(in_table=newLithTable, field_name="SEDIMENT", field_type="TEXT", field_length=7,
                              field_alias="Simplified Sediment Class", field_domain="Simplified")
    arcpy.management.AddField(in_table=newLithTable, field_name="LITH_AGG", field_type="TEXT", field_length=4,
                              field_alias="Lithology Aggregate Unit", field_domain="LithAgg")
    arcpy.management.AddField(in_table=newLithTable, field_name="COLOR", field_type="TEXT", field_length=50,
                              field_alias="Color", field_domain="Color")
    arcpy.management.AddField(in_table=newLithTable, field_name="PRIM_LITH", field_type="TEXT", field_length=50,
                              field_alias="Primary Lithology", field_domain="PrimaryLith")
    arcpy.management.AddField(in_table=newLithTable, field_name="TEXTURE", field_type="TEXT", field_length=50,
                              field_alias="Sediment Texture", field_domain="Texture")
    arcpy.management.AddField(in_table=newLithTable, field_name="CONSISTENCY", field_type="TEXT", field_length=50,
                              field_alias="Consistency", field_domain="Consistency")
    arcpy.management.AddField(in_table=newLithTable, field_name="SEC_LITH", field_type="TEXT", field_length=50,
                              field_alias="Lithology Modifier", field_domain="SecondaryLith")
    arcpy.management.AddField(in_table=newLithTable, field_name="THIRD_LITH", field_type="TEXT", field_length=50,
                              field_alias="Secondary Modifier", field_domain="SecondaryLith")
    arcpy.management.AddField(in_table=newLithTable, field_name="DEPTH_TOP", field_type="DOUBLE",field_alias="Depth: Top (ft)")
    arcpy.management.AddField(in_table=newLithTable, field_name="DEPTH_BOT", field_type="DOUBLE",field_alias="Depth: Bottom (ft)")
    arcpy.management.AddField(in_table=newLithTable, field_name="THICKNESS", field_type="DOUBLE",field_alias="Thickness of Stratum (ft)")
    arcpy.management.AddField(in_table=newLithTable, field_name="AQUIFER", field_type="TEXT", field_length=6,
                              field_alias="Aquifer Type", field_domain="LithAquifer")
    arcpy.management.AddField(in_table=newLithTable, field_name="FIRST_BDRK", field_type="TEXT", field_length=3,
                              field_alias="First True Bedrock Unit Encountered?", field_domain="FirstBDKR")
    arcpy.management.AddField(in_table=newLithTable, field_name="GROUP_NAME", field_type="TEXT", field_length=3,
                              field_alias="Group Name", field_domain="GroupNames")
    arcpy.management.AddField(in_table=newLithTable, field_name="AGE", field_type="TEXT", field_length=50,
                              field_alias="Age of Lithology (Name)", field_domain="Age")
    arcpy.management.AddField(in_table=newLithTable, field_name="DEP_ENV", field_type="TEXT", field_length=50,
                              field_alias="Depositional Environment")
    arcpy.management.AddField(in_table=newLithTable, field_name="GEO_COMMENTS", field_type="TEXT", field_length=10000,
                              field_alias="Lithology Comments")
    arcpy.management.AddField(in_table=newLithTable, field_name="VERIFIED", field_type="TEXT", field_length=1,
                              field_alias="Data Verified by MGS?", field_domain="Verification")
    arcpy.management.AddGlobalIDs(in_datasets=newLithTable)
    simpleExpression = ("""var aggregate = $feature.LITH_AGG;
    var sediment = When(Equals(aggregate,"UNK"),"UNK",
                        Equals(aggregate,"BDRK"),"BEDROCK",
                        Equals(aggregate,"CLAY") || Equals(aggregate,"FSAN"),"FINE",
                        Equals(aggregate,"GRAV") || Equals(aggregate,"SAND") || Equals(aggregate,"SAGR"),"COARSE",
                        Equals(aggregate,"CLSA") || Equals(aggregate,"DIAM"),"MIXED",
                        Equals(aggregate,"TOPS") || Equals(aggregate,"ORGA"),"ORGANIC",
                        "UNK");
    return sediment""")
    drillerExpression = ("""var driller = [$feature.COLOR,$feature.PRIM_LITH,$feature.TEXTURE,$feature.SEC_LITH,$feature.THIRD_LITH,$feature.CONSISTENCY];
    var desc = [];
    for (var i in driller) {
        if (!IsEmpty(driller[i])){
            desc[Count(desc)] = Upper(driller[i]);
        }
    }
    return Concatenate(desc," ")""")
    ageExpression = ("""var group = $feature.GROUP_NAME;
    var age = When(Equals(group,"AGR") || Equals(group,"AUM"),"PC-ARC-EARL",
                   Equals(group,"GIF"),"PH-PAL-EDEV",
                   Equals(group,"CWT") || Equals(group,"MAR") || Equals(group,"SUN"), "PH-PAL-EMIS",
                   Equals(group,"LOD") || Equals(group,"NRS") || Equals(group,"OND") || Equals(group,"PDC") || Equals(group,"SHD") || Equals(group,"SLM"),"PH-PAL-EORD",
                   Equals(group,"PSS"),"PH-PAL-EPLM",
                   Equals(group,"SAG"),"PH-PAL-EPEN",
                   Equals(group,"MGF") || Equals(group,"BDG") || Equals(group,"BIF") || Equals(group,"CHO") || Equals(group, "DCF") || Equals(group, "EVC") || Equals(group,"GDQ") || Equals(group,"HEM") || Equals(group, "IIF") || Equals(group, "MCG") || Equals(group, "NIF") || Equals(group,"PAF") || Equals(group,"PRG") || Equals(group,"RAD") || Equals(group,"RIF") || Equals(group,"SAQ") || Equals(group,"AMA"),"PC-PRO-EARL",
                   Equals(group,"CHS") || Equals(group,"CAG") || Equals(group,"MND"),"PH-PAL-ESIL",
                   Equals(group,"AVS") || Equals(group,"QUF"),"PC-ARC-LATE",
                   Equals(group,"DSS") || Equals(group,"ECM") || Equals(group,"FRS") || Equals(group,"LSG") || Equals(group,"MSS") || Equals(group,"MUN") || Equals(group,"TMP"), "PH-PAL-LCAM",
                   Equals(group,"ANT") || Equals(group,"BED") || Equals(group,"BER") || Equals(group,"ELL"), "PH-PAL-LDEV",
                   Equals(group,"BAY") || Equals(group,"GRG") || Equals(group,"MIF") || Equals(group,"NSS"), "PH-PAL-LMIS",
                   Equals(group,"QUS") || Equals(group,"RIG") || Equals(group,"USM") || Equals(group,"BHD") || Equals(group,"STF"), "PH-PAL-LORD",
                   Equals(group,"GRF"), "PH-PAL-LPEN",
                   Equals(group,"BIG") || Equals(group,"SAL") || Equals(group,"PAC") || Equals(group,"SID"), "PH-PAL-LSIL",
                   Equals(group,"SBL"), "PH-PAL-MDLD",
                   Equals(group,"INT"), "PC-PRO-MESO",
                   Equals(group,"MAC"), "PH-PAL-MDLS",
                   Equals(group,"ALL") || Equals(group,"AMF") || Equals(group,"BLS") || Equals(group,"BBF") || Equals(group,"DRG") || Equals(group,"DDL") || Equals(group,"LUF") || Equals(group,"RCL") || Equals(group,"TRG") || Equals(group,"SSS"), "PH-PAL-MDEV",
                   Equals(group,"RBD"), "PH-MES-MJUR",
                   Equals(group,"BRG") || Equals(group,"CSM") || Equals(group,"GLM") || Equals(group,"JSS") || Equals(group,"SPS") || Equals(group,"TRN"), "PH-PAL-MORD",
                   Equals(group,"FSS") || Equals(group,"JAC") || Equals(group,"NSF") || Equals(group,"CHC") || Equals(group,"OBF") || Equals(group,"PLV") || Equals(group,"SCF"), "PC-PRO-MIDL",
                   Equals(group,"BBG") || Equals(group,"ENG") || Equals(group,"MQG") || Equals(group,"NIA"), "PH-PAL-MSIL",
                   Equals(group,"GLA"),"PH-CEN-PLEI",
                   Equals(group,"PRE"),"PC",
                   Equals(group,"UNK"),"UNK","UNK")
    return age""")
    arcpy.management.AddAttributeRule(in_table=newLithTable,
                                      name="SimpleLith",
                                      type="CALCULATION",
                                      script_expression=simpleExpression,
                                      field="SEDIMENT",
                                      triggering_events=["INSERT","UPDATE"])
    arcpy.management.AddAttributeRule(in_table=newLithTable,
                                      name="DrillerDesc",
                                      type="CALCULATION",
                                      script_expression=drillerExpression,
                                      field="DRLLR_DESC",
                                      triggering_events=["INSERT", "UPDATE"])
    arcpy.management.AddAttributeRule(in_table=newLithTable,
                                      name="Age",
                                      type="CALCULATION",
                                      script_expression=ageExpression,
                                      field="AGE",
                                      triggering_events=["INSERT", "UPDATE"])

except:
    AddMsgAndPrint("ERROR 020: Failed to make new table with standard fields",2)
    raise SystemError

try:
    # Now we merge all the data into the new table...
    AddMsgAndPrint("  Appending data from {} to {}...".format(os.path.splitext(os.path.basename(lithTable))[0],
                                                              os.path.splitext(os.path.basename(newLithTable))[0]))
    lithMappings = ""
    lithMappings = arcpy.FieldMappings()
    lithMappings.addTable(newLithTable)
    appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="WELLID", newField="WELLID",
                            newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="SEQ_NUM", newField="SEQ_NUM",
                            newFieldType="SHORT")
    appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="PRIM_LITH", newField="PRIM_LITH",
                            newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="DEPTH", newField="DEPTH_BOT",
                            newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="THICKNESS", newField="THICKNESS",
                            newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="COLOR", newField="COLOR",
                            newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="SEC_DESC", newField="SEC_LITH",
                            newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="CON", newField="CONSISTENCY",
                            newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="AQ", newField="AQUIFER",
                            newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="AGG", newField="LITH_AGG",
                            newFieldType="TEXT")
    arcpy.management.Append(lithTable, newLithTable, "NO_TEST", lithMappings, "")
except:
    AddMsgAndPrint("ERROR 021: Failed to append old data into the new table",2)
    raise SystemError
try:
    # We can now fill in some of the fields using the formatted data...
    firstBDRKValue(bdrkTable=newLithTable, origTable=pointsTable, relate="WELLID", seq="SEQ_NUM", primLith="AQUIFER",
                   firstBDRK="FIRST_BDRK")
    arcpy.management.CalculateField(in_table=newLithTable,
                                    field="DEPTH_TOP",
                                    expression="!DEPTH_BOT! - !THICKNESS!")
    validationTable = "https://services1.arcgis.com/vFQXQuqACTPxa4Yc/arcgis/rest/services/ReviewTable/FeatureServer/0"
    arcpy.management.JoinField(in_data=newLithTable, in_field="WELLID", join_table=validationTable, join_field="WELLID",fields="REVIEW;PHASE")
    reviewBlock = ("""def review(oldReview,phase):
        if (phase == "LV" or phase == "LA" or phase == "EL"):
            return "N"
        else:
            if oldReview == "Y":
                return "Y"
            elif oldReview == "N":
                return "N"
            else:
                return "N"
                """)
    arcpy.management.CalculateField(in_table=newLithTable,
                                    field="VERIFIED",
                                    expression="review(!REVIEW!,!PHASE!)",
                                    code_block=reviewBlock)
    arcpy.management.DeleteField(newLithTable,["REVIEW","PHASE"])
    groupBlock = ("""def groupName(group,aq):
        if group is not None:
            return group
        else:
            if (aq.startswith("R") or aq.startswith("U")):
                return "UNK"
            else:
                return "GLA"
    """)
    arcpy.management.CalculateField(in_table=newLithTable,
                                    field="GROUP_NAME",
                                    expression="groupName(!GROUP_NAME!,!AQUIFER!)",
                                    code_block=groupBlock)
except:
    AddMsgAndPrint("ERROR 022: Failed to fill in empty fields",2)
    raise SystemError

try:
    AddMsgAndPrint("Finding lithologies with first bedrock unit encountered in {}...".format(os.path.splitext(os.path.basename(newLithTable))[0]))
    bdrkLithTable = os.path.join(geologyLoc, os.path.splitext(os.path.basename(newLithTable))[0] + "_FIRST_BDRK")
    arcpy.analysis.TableSelect(newLithTable, bdrkLithTable, "FIRST_BDRK = 'YES'")
    arcpy.management.AddAttributeRule(in_table=bdrkLithTable,
                                      name="SimpleLith",
                                      type="CALCULATION",
                                      script_expression=simpleExpression,
                                      field="SEDIMENT",
                                      triggering_events=["INSERT", "UPDATE"])
    arcpy.management.AddAttributeRule(in_table=bdrkLithTable,
                                      name="DrillerDesc",
                                      type="CALCULATION",
                                      script_expression=drillerExpression,
                                      field="DRLLR_DESC",
                                      triggering_events=["INSERT", "UPDATE"])
    arcpy.management.AddAttributeRule(in_table=bdrkLithTable,
                                      name="Age",
                                      type="CALCULATION",
                                      script_expression=ageExpression,
                                      field="AGE",
                                      triggering_events=["INSERT", "UPDATE"])
    AddMsgAndPrint("  {} contains all the bedrock lithologies, and is written to {}".format(os.path.splitext(os.path.basename(bdrkLithTable))[0],os.path.dirname(bdrkLithTable)))
except:
    AddMsgAndPrint("ERROR 023: Failed to export 'no record' and 'first bedrock' lithology tables",2)
    raise SystemError

try:
    AddMsgAndPrint("Adding tables and cleaning scratch geodatabase...")
    pm = prj.activeMap
    pm.addDataFromPath(newLithTable)
    pm.addDataFromPath(bdrkLithTable)
    prj.save()
    arcpy.management.Delete(lithTable)
except:
    AddMsgAndPrint("ERROR 024: Failed to import lithology tables and/or failed to clean geodatabase",2)
    raise SystemError

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("BEGIN FORMATTING THE WATER WELL POINTS FEATURE CLASS...")
try:
    wwName = projectName + "_WW_Points"
    arcpy.AddMessage("Extracting elevation data to {}...".format(os.path.splitext(os.path.basename(pointsShape))[0]))
    if arcpy.Describe(pointsShape).spatialReference == "GCS_WGS_1984":
        eventProject = os.path.join(scratchDir, os.path.splitext(os.path.basename(pointsShape))[0] + '_project')
        arcpy.AddMessage("- Projecting shapefile to NAD 1983 Hotine projection")
        arcpy.management.Project(pointsShape, eventProject, "", "WGS_1984_(ITRF00)_To_NAD_1983",
                                 "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984',SPHEROID['WGS_1984',6378137.0,298.257223563]],PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]",
                                 "NO_PRESERVE_SHAPE", "", "NO_VERTICAL")
        if standard_OR_no == "Non-Standard Project Area":
            wellsSelect = arcpy.management.SelectLayerByLocation(eventProject, 'COMPLETELY_WITHIN', featExtent, None, 'NEW_SELECTION', '')
            arcpy.management.MakeFeatureLayer(wellsSelect, "TempWells")
        if standard_OR_no == "Standard 2-5 Mile Project":
            wellsSelect = arcpy.management.SelectLayerByLocation(eventProject, 'COMPLETELY_WITHIN', buff5mile, None, 'NEW_SELECTION', '')
            arcpy.management.MakeFeatureLayer(wellsSelect, "TempWells")
        eventExtract = os.path.join(scratchDir, os.path.splitext(os.path.basename(pointsShape))[0] + '_extract')
        arcpy.sa.ExtractValuesToPoints("TempWells",prjDEM,eventExtract,"","")
    else:
        if standard_OR_no == "Non-Standard Project Area":
            wellsSelect = arcpy.management.SelectLayerByLocation(pointsShape, 'COMPLETELY_WITHIN', featExtent, None, 'NEW_SELECTION', '')
            arcpy.management.MakeFeatureLayer(wellsSelect,"TempWells")
        if standard_OR_no == "Standard 2-5 Mile Project":
            wellsSelect = arcpy.management.SelectLayerByLocation(pointsShape, 'COMPLETELY_WITHIN', buff5mile, None, 'NEW_SELECTION', '')
            arcpy.management.MakeFeatureLayer(wellsSelect, "TempWells")
        eventExtract = os.path.join(scratchDir, os.path.splitext(os.path.basename(pointsShape))[0] + '_extract')
        arcpy.sa.ExtractValuesToPoints("TempWells",prjDEM,eventExtract,"","")
except:
    arcpy.AddError("ERROR 025: Failed to extract elevation values to {}".format(os.path.splitext(os.path.basename(pointsShape))[0]))
    arcpy.AddMessage("Error is likely too many locations outside of the elevation DEM.")
    raise SystemError

try:
    AddMsgAndPrint("- Formatting {} to prepare for appending...".format(os.path.splitext(os.path.basename(eventExtract))[0]))
    with arcpy.da.UpdateCursor(eventExtract, "RASTERVALU") as cursor:
        for row in cursor:
            if row[0] == None:
                cursor.deleteRow()
        del row, cursor
except:
    AddMsgAndPrint("ERROR 026: Failed to format {}".format(os.path.splitext(os.path.basename(eventExtract))[0]),2)
    raise SystemError
try:
    AddMsgAndPrint("Creating new feature class ({}) with appropriate fields...".format(wwName))
    arcpy.management.CreateFeatureclass(geologyLoc, wwName, "POINT", "", "DISABLED", "DISABLED", "", "", "0", "0", "0")
    outWWpoints = os.path.join(geologyLoc, wwName)
    arcpy.management.AddField(in_table=outWWpoints,field_name="WELLID",field_type="TEXT",field_length=12,
                              field_alias="Well ID")
    arcpy.management.AddField(in_table=outWWpoints, field_name="PERMIT_NUM", field_type="TEXT", field_length=20,
                              field_alias="Permit Number")
    arcpy.management.AddField(in_table=outWWpoints, field_name="COUNTY", field_type="TEXT", field_length=30,
                              field_alias="County")
    arcpy.management.AddField(in_table=outWWpoints, field_name="TOWNSHIP", field_type="TEXT", field_length=50,
                              field_alias="Township")
    arcpy.management.AddField(in_table=outWWpoints, field_name="PLSS_TOWN", field_type="TEXT", field_length=3,
                              field_alias="PLSS Township")
    arcpy.management.AddField(in_table=outWWpoints, field_name="PLSS_RANGE", field_type="TEXT", field_length=3,
                              field_alias="PLSS Range")
    arcpy.management.AddField(in_table=outWWpoints, field_name="PLSS_SECTION", field_type="SHORT",
                              field_alias="PLSS Section")
    arcpy.management.AddField(in_table=outWWpoints, field_name="WELL_ADDR", field_type="TEXT", field_length=50,
                              field_alias="Well Address")
    arcpy.management.AddField(in_table=outWWpoints, field_name="WELL_CITY", field_type="TEXT", field_length=30,
                              field_alias="Well Address: City")
    arcpy.management.AddField(in_table=outWWpoints, field_name="WELL_ZIP", field_type="TEXT", field_length=9,
                              field_alias="Well Address: Zip Code")
    arcpy.management.AddField(in_table=outWWpoints, field_name="OWNER_NAME", field_type="TEXT", field_length=30,
                              field_alias="Owner Name")
    arcpy.management.AddField(in_table=outWWpoints, field_name="COMPL_DEPTH", field_type="DOUBLE",
                              field_alias="Completion Depth (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="BOREH_DEPTH", field_type="DOUBLE",
                              field_alias="Borehole Depth (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="WELL_LABEL", field_type="TEXT", field_length=255,
                              field_alias="Well Label")
    arcpy.management.AddField(in_table=outWWpoints, field_name="WELL_TYPE", field_type="TEXT", field_length=6,
                              field_alias="Well Type", field_domain="WellType")
    arcpy.management.AddField(in_table=outWWpoints, field_name="TYPE_OTHER", field_type="TEXT", field_length=30,
                              field_alias="Well Type: Other")
    arcpy.management.AddField(in_table=outWWpoints, field_name="WEL_STATUS", field_type="TEXT", field_length=6,
                              field_alias="Well Status", field_domain="WellStatus")
    arcpy.management.AddField(in_table=outWWpoints, field_name="STATUS_OTH", field_type="TEXT", field_length=254,
                              field_alias="Well Status: Other")
    arcpy.management.AddField(in_table=outWWpoints, field_name="WSSN", field_type="DOUBLE",
                              field_alias="WSSN")
    arcpy.management.AddField(in_table=outWWpoints, field_name="DRILLER_ID", field_type="TEXT", field_length=10,
                              field_alias="Driller ID")
    arcpy.management.AddField(in_table=outWWpoints, field_name="DRILL_METH", field_type="TEXT", field_length=6,
                              field_alias="Drilling Method", field_domain="Drilling")
    arcpy.management.AddField(in_table=outWWpoints, field_name="METH_OTHER", field_type="TEXT", field_length=30,
                              field_alias="Drilling Method: Other")
    arcpy.management.AddField(in_table=outWWpoints, field_name="CONST_DATE", field_type="DATE",
                              field_alias="Completion Date")
    arcpy.management.AddField(in_table=outWWpoints, field_name="CASE_TYPE", field_type="TEXT", field_length=6,
                              field_alias="Casing Type", field_domain="CasingType")
    arcpy.management.AddField(in_table=outWWpoints, field_name="CASE_OTHER", field_type="TEXT", field_length=30,
                              field_alias="Casing Type: Other")
    arcpy.management.AddField(in_table=outWWpoints, field_name="CASE_DIA", field_type="DOUBLE",
                              field_alias="Casing Diameter (inches)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="CASE_DEPTH", field_type="DOUBLE",
                              field_alias="Casing Depth (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="SCREEN_FRM", field_type="DOUBLE",
                              field_alias="Screen Top (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="SCREEN_TO", field_type="DOUBLE",
                              field_alias="Screen Bottom (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="FLOWING", field_type="TEXT", field_length=1,
                              field_alias="Artesian Well?", field_domain="Verification")
    arcpy.management.AddField(in_table=outWWpoints, field_name="AQ_TYPE", field_type="TEXT", field_length=6,
                              field_alias="Aquifer Type", field_domain="WellAquifer")
    arcpy.management.AddField(in_table=outWWpoints, field_name="TEST_DEPTH", field_type="DOUBLE",
                              field_alias="Pump Test: Depth (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="TEST_HOURS", field_type="DOUBLE",
                              field_alias="Pump Test: Duration (hours)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="TEST_RATE", field_type="DOUBLE",
                              field_alias="Pump Test: Rate (GPM)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="TEST_METHD", field_type="TEXT", field_length=6,
                              field_alias="Pump Test: Method", field_domain="TestMethod")
    arcpy.management.AddField(in_table=outWWpoints, field_name="TEST_OTHER", field_type="TEXT", field_length=30,
                              field_alias="Pump Test: Method (Other)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="GROUT", field_type="TEXT", field_length=1,
                              field_alias="Well Grouted?", field_domain="Verification")
    arcpy.management.AddField(in_table=outWWpoints, field_name="PMP_CPCITY", field_type="DOUBLE",
                              field_alias="Pump Capacity (GPM)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="LATITUDE", field_type="DOUBLE",
                              field_alias="Latitude")
    arcpy.management.AddField(in_table=outWWpoints, field_name="LONGITUDE", field_type="DOUBLE",
                              field_alias="Longitude")
    arcpy.management.AddField(in_table=outWWpoints, field_name="UTM_E", field_type="DOUBLE",
                              field_alias="UTM: Easting")
    arcpy.management.AddField(in_table=outWWpoints, field_name="UTM_N", field_type="DOUBLE",
                              field_alias="UTM: Northing")
    arcpy.management.AddField(in_table=outWWpoints, field_name="WW_ELEV", field_type="DOUBLE",
                              field_alias="Wellogic Elevation (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="DEM_ELEV", field_type="DOUBLE",
                              field_alias="DEM Elevation (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="SWL", field_type="DOUBLE",
                              field_alias="Static Water Level (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="DEPTH_2_BDRK", field_type="DOUBLE",
                              field_alias="Depth to Top of Bedrock (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="SWL_ELEV", field_type="DOUBLE",
                              field_alias="SWL Elevation (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="BDRK_ELEV", field_type="DOUBLE",
                              field_alias="Bedrock Elevation (ft)")
    arcpy.management.AddField(in_table=outWWpoints, field_name="RECORD_LINK", field_type="TEXT", field_length=10000,
                              field_alias="EGLE PDF Link")
    arcpy.management.AddField(in_table=outWWpoints, field_name="VERIFIED", field_type="TEXT", field_length=1,
                              field_alias="Data Verified by MGS?", field_domain="Verification")
    arcpy.management.AddGlobalIDs(in_datasets=outWWpoints)
    labelBlock = ("""var type = $feature.WELL_TYPE;
    var aq = $feature.AQ_TYPE;
    var label = When(Equals(aq,"DRIFT")&&Equals(type,"TY1PU"),"Drift: Type 1 Public Supply",
                    Equals(aq,"DRIFT")&&Equals(type,"TY2PU"),"Drift: Type 2 Public Supply",
                    Equals(aq,"DRIFT")&&Equals(type,"TY3PU"),"Drift: Type 3 Public Supply",
                    Equals(aq,"DRIFT")&&(Equals(type,"HEATP") || Equals(type,"HEATRE") || Equals(type,"HEATSU") || Equals(type,"HOSHLD") || Equals(type,"INDUS") || Equals(type,"IRRI") || Equals(type,"OTH") || Equals(type,"TESTW") || Equals(type,"UNK")),"Drift: All Other Wells",
                    Equals(aq,"ROCK")&&Equals(type,"TY1PU"),"Bedrock: Type 1 Public Supply",
                    Equals(aq,"ROCK")&&Equals(type,"TY2PU"),"Bedrock: Type 2 Public Supply",
                    Equals(aq,"ROCK")&&Equals(type,"TY3PU"),"Bedrock: Type 3 Public Supply",
                    Equals(aq,"ROCK")&&(Equals(type,"HEATP") || Equals(type,"HEATRE") || Equals(type,"HEATSU") || Equals(type,"HOSHLD") || Equals(type,"INDUS") || Equals(type,"IRRI") || Equals(type,"OTH") || Equals(type,"TESTW") || Equals(type,"UNK")),"Bedrock: All Other Wells",
                    Equals(aq,"UNK")&&Equals(type,"TY1PU"),"Unknown Aquifer: Type 1 Public Supply",
                    Equals(aq,"UNK")&&Equals(type,"TY2PU"),"Unknown Aquifer: Type 2 Public Supply",
                    Equals(aq,"UNK")&&Equals(type,"TY3PU"),"Unknown Aquifer: Type 3 Public Supply",
                    Equals(aq,"UNK")&&(Equals(type,"HEATP") || Equals(type,"HEATRE") || Equals(type,"HEATSU") || Equals(type,"HOSHLD") || Equals(type,"INDUS") || Equals(type,"IRRI") || Equals(type,"OTH") || Equals(type,"TESTW") || Equals(type,"UNK")),"Unknown Aquifer: All Other Wells","Unknown Aquifer: All Other Wells");
    return label;""")
    arcpy.management.AddAttributeRule(in_table=outWWpoints,
                                      name="WellLabel",
                                      type="CALCULATION",
                                      script_expression=labelBlock,
                                      field="WELL_LABEL",
                                      triggering_events=["INSERT", "UPDATE"])
except:
    AddMsgAndPrint("ERROR 027: Failed to create final dataset template",2)
    raise SystemError
try:
    AddMsgAndPrint("Appending data from {} to {}...".format(os.path.splitext(os.path.basename(eventExtract))[0],os.path.splitext(os.path.basename(outWWpoints))[0]))
    wwMappings = ""
    wwMappings = arcpy.FieldMappings()
    wwMappings.addTable(outWWpoints)
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="RASTERVALU",
                            newField="DEM_ELEV", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="ELEVATION",
                            newField="WW_ELEV", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="WELL_DEPTH",
                            newField="COMPL_DEPTH", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="CONST_DATE",
                            newField="CONST_DATE", newFieldType="DATE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="TOWN",
                            newField="PLSS_TOWN", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="RANGE",
                            newField="PLSS_RANGE", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="SECTION",
                            newField="PLSS_SECTION", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="WELLID",
                            newField="WELLID", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="PERMIT_NUM",
                            newField="PERMIT_NUM", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="COUNTY",
                            newField="COUNTY", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="TOWNSHIP",
                            newField="TOWNSHIP", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="WELL_ADDR",
                            newField="WELL_ADDR", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="WELL_CITY",
                            newField="WELL_CITY", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="WELL_ZIP",
                            newField="WELL_ZIP", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="OWNER_NAME",
                            newField="OWNER_NAME", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="WELL_TYPE",
                            newField="WELL_TYPE", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="TYPE_OTHER",
                            newField="TYPE_OTHER", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="WEL_STATUS",
                            newField="WEL_STATUS", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="STATUS_OTH",
                            newField="STATUS_OTH", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="WSSN",
                            newField="WSSN", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="DRILLER_ID",
                            newField="DRILLER_ID", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="DRILL_METH",
                            newField="DRILL_METH", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="METH_OTHER",
                            newField="METH_OTHER", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="CASE_TYPE",
                            newField="CASE_TYPE", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="CASE_OTHER",
                            newField="CASE_OTHER", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="CASE_DIA",
                            newField="CASE_DIA", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="CASE_DEPTH",
                            newField="CASE_DEPTH", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="SCREEN_FRM",
                            newField="SCREEN_FRM", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="SCREEN_TO",
                            newField="SCREEN_TO", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="SWL",
                            newField="SWL", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="FLOWING",
                            newField="FLOWING", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="AQ_TYPE",
                            newField="AQ_TYPE", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="TEST_DEPTH",
                            newField="TEST_DEPTH", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="TEST_HOURS",
                            newField="TEST_HOURS", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="TEST_RATE",
                            newField="TEST_RATE", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="TEST_METHD",
                            newField="TEST_METHD", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="TEST_OTHER",
                            newField="TEST_OTHER", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="GROUT",
                            newField="GROUT", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="PMP_CPCITY",
                            newField="PMP_CPCITY", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="LATITUDE",
                            newField="LATITUDE", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=wwMappings, oldTable=eventExtract, oldField="LONGITUDE",
                            newField="LONGITUDE", newFieldType="DOUBLE")
    arcpy.management.Append(eventExtract, outWWpoints, "NO_TEST", wwMappings, "")
except:
    AddMsgAndPrint("ERROR 028: Failed to append {} to {}".format(os.path.splitext(os.path.basename(eventExtract))[0],os.path.splitext(os.path.basename(outWWpoints))[0]),2)
    raise SystemError
try:
    AddMsgAndPrint("Formatting the empty fields in {}...".format(os.path.splitext(os.path.basename(outWWpoints))[0]))
    maxDepthTable = os.path.join(scratchDir, "{}_MaxDepth".format(projectName))
    arcpy.analysis.Statistics(in_table=newLithTable,
                              out_table=maxDepthTable,
                              statistics_fields=[["DEPTH_BOT", "MAX"]],
                              case_field="WELLID")
    arcpy.management.JoinField(outWWpoints, "WELLID", bdrkLithTable, "WELLID", "DEPTH_TOP")
    arcpy.management.JoinField(outWWpoints, "WELLID", maxDepthTable, "WELLID", "MAX_DEPTH_BOT")
    arcpy.management.CalculateField(in_table=outWWpoints,
                                    field="DEPTH_2_BDRK",
                                    expression="!DEPTH_TOP!")
    boreDepth = ("""def boreDepth(bore,compl):
                if bore is None:
                    return compl
                else:
                    return bore
            """)
    arcpy.management.CalculateField(in_table=outWWpoints,
                                    field="BOREH_DEPTH",
                                    expression="boreDepth(!MAX_DEPTH_BOT!,!COMPL_DEPTH!)",
                                    code_block=boreDepth)

    wellAQBlock = ("""def aq(top,bottom,bdrk):
        if bdrk is None:
            if top > 0 and bottom > 0:
                return "DRIFT"
            else:
                return "UNK"
        else:
            if (top == 0 and bottom == 0 and bdrk != 0):
                return "ROCK"
            if (bottom >= bdrk and bdrk !=0):
                return "ROCK"
            if bottom <= bdrk:
                return "DRIFT"
            else:
                return "UNK"
    """)
    arcpy.management.CalculateField(in_table=outWWpoints,
                                    field="AQ_TYPE",
                                    expression="aq(!SCREEN_FRM!,!SCREEN_TO!,!DEPTH_2_BDRK!)",
                                    code_block=wellAQBlock)
    arcpy.management.CalculateField(in_table=outWWpoints,
                                    field="BDRK_ELEV",
                                    expression="!DEM_ELEV! - !DEPTH_2_BDRK!")
    arcpy.management.CalculateField(in_table=outWWpoints,
                                    field="SWL_ELEV",
                                    expression="!DEM_ELEV! - !SWL!")
    arcpy.management.CalculateGeometryAttributes(in_features=outWWpoints,
                                                 geometry_property=[["UTM_E","POINT_X"],["UTM_N","POINT_Y"]],
                                                 length_unit="METERS")
    arcpy.management.CalculateField(outWWpoints, "RECORD_LINK",
                                    '"https://www.egle.state.mi.us/wellogic/ReportProxy.aspx/?/WELLOGIC/WELLOGIC/user_Well%20Record&rs:Command=Render&rs:Format=PDF&wellLogID=" + $feature.WELLID',
                                    "ARCADE")
    arcpy.management.JoinField(in_data=outWWpoints, in_field="WELLID", join_table=validationTable, join_field="WELLID",
                               fields="REVIEW")
    locRevBlock = ("""def review(oldReview):
        if oldReview == "Y":
            return "Y"
        elif oldReview == "N":
            return "N"
        else:
            return "N"
    """)
    arcpy.management.CalculateField(in_table=outWWpoints,
                                    field="VERIFIED",
                                    expression="review(!REVIEW!)",
                                    code_block=locRevBlock)
    arcpy.management.DeleteField(outWWpoints,["DEPTH_TOP","MAX_DEPTH_BOT","REVIEW"])
except:
    AddMsgAndPrint("ERROR 029: Failed to format new points table",2)
    raise SystemError

try:
    pm = prj.activeMap
    try:
        csm = prj.listMaps('03_Layout Map - Cross Section')[0]
        mm = prj.listMaps('02_Layout Map - Main')[0]
        AddMsgAndPrint(
            "- Adding {} to {} and {}...".format(os.path.splitext(os.path.basename(outWWpoints))[0], mm.name, csm.name))
        mm.addDataFromPath(outWWpoints)
        csm.addDataFromPath(outWWpoints)
        prj.save()
        wwSymbol(map=mm,feature=outWWpoints)
        wwSymbol(map=csm, feature=outWWpoints)
    except:
        AddMsgAndPrint("Maps do not exist or is not supported. Passing to next step...")
        pass
except:
    AddMsgAndPrint("ERROR 030: Failed to add data into the respective maps",2)
    raise SystemError

try:
    arcpy.AddMessage("- Creating copies of {} for use in generating groundwater surfaces...".format(
        os.path.splitext(os.path.basename(outWWpoints))[0]))
    orig_count = arcpy.management.GetCount(outWWpoints)
    arcpy.AddMessage("  *Original copy of water well points has {} records".format(orig_count))
    gwlName = wwName + "_GWL_USABLE"
    gwlWW = os.path.join(geologyLoc, gwlName)
    arcpy.management.CopyFeatures(outWWpoints, gwlWW)
    arcpy.management.AssignDomainToField(in_table=gwlWW, field_name="WELL_TYPE", domain_name="WellType")
    arcpy.management.AssignDomainToField(in_table=gwlWW, field_name="WEL_STATUS", domain_name="WellStatus")
    arcpy.management.AssignDomainToField(in_table=gwlWW, field_name="DRILL_METH", domain_name="Drilling")
    arcpy.management.AssignDomainToField(in_table=gwlWW, field_name="CASE_TYPE", domain_name="CasingType")
    arcpy.management.AssignDomainToField(in_table=gwlWW, field_name="FLOWING", domain_name="Verification")
    arcpy.management.AssignDomainToField(in_table=gwlWW, field_name="AQ_TYPE", domain_name="WellAquifer")
    arcpy.management.AssignDomainToField(in_table=gwlWW, field_name="TEST_METHD", domain_name="TestMethod")
    arcpy.management.AssignDomainToField(in_table=gwlWW, field_name="GROUT", domain_name="Verification")
    arcpy.management.AssignDomainToField(in_table=gwlWW, field_name="VERIFIED", domain_name="Verification")
    arcpy.management.CalculateField(in_table=gwlWW,
                                    field="WELL_LABEL",
                                    expression=labelBlock,
                                    expression_type="ARCADE")

    # Update the GWL Table
    with arcpy.da.UpdateCursor(gwlWW, "VERIFIED") as cursor:
        for row in cursor:
            if row[0] == "Y":
                pass
            else:
                cursor.deleteRow()
        del row, cursor
    arcpy.AddMessage('  Filtering anomalous SWL values (greater than 999)...')
    with arcpy.da.UpdateCursor(gwlWW, ["SWL", "FLOWING", "WELLID"]) as cursor:
        for row in cursor:
            if row[0] > 998:
                row[0] = None
                cursor.updateRow(row)
            if (row[0] == 0 and row[1] == "Y"):
                arcpy.AddWarning('      {} has an 0 swl and is flowing. Please review for validity...'.format(row[2]))
            del row
        del cursor
    swlCodeBlock = (
        """def finalSWL(swl,elev):
                if (swl == None):
                    pass
                else:
                    return elev-swl""")
    arcpy.management.CalculateField(in_table=gwlWW,
                                    field="SWL_ELEV",
                                    expression="finalSWL(!SWL!,!DEM_ELEV!)",
                                    code_block=swlCodeBlock)
    gwlcopy_count = arcpy.management.GetCount(gwlWW)
    arcpy.AddMessage("  *Groundwater copy of water points has {} records.".format(gwlcopy_count))
except:
    AddMsgAndPrint("ERROR 031: Failed to copy {} for editing".format(os.path.splitext(os.path.basename(outWWpoints))[0]),2)
    raise SystemError

try:
    arcpy.AddMessage("Adding tables and cleaning scratch geodatabase...")
    pm = prj.activeMap
    pm.addDataFromPath(gwlWW)
    prj.save()
    wwSymbol(map=pm,feature=gwlWW)
    if arcpy.Describe(pointsShape).spatialReference == "GCS_WGS_1984":
        arcpy.management.Delete(eventProject)
    arcpy.management.Delete([eventExtract])
except:
    AddMsgAndPrint("ERROR 032: Failed to add tables and clean geodatabase for water well points",2)
    raise SystemError

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("BEGIN FORMATTING THE SCREEN TABLE...")
try:
    arcpy.AddMessage("Extracting screen information in the project area...")
    outScreen = os.path.join(geologyLoc, os.path.splitext(os.path.basename(outWWpoints))[0] + '_SCREENS')
    arcpy.management.CopyFeatures(outWWpoints, outScreen)
    with arcpy.da.UpdateCursor(outScreen, ["SCREEN_FRM", "SCREEN_TO"]) as cursor:
        for row in cursor:
            if (row[0] == 0 and row[1] == 0):
                cursor.deleteRow()
    del row
    del cursor
except:
    AddMsgAndPrint("ERROR 033: Failed to extract screen information",2)
    raise SystemError
try:
    arcpy.AddMessage("Creating table for the screens in the project area...")
    eventScreens = os.path.splitext(os.path.basename(outScreen))[0] + "_EVENT"
    arcpy.conversion.TableToTable(outScreen, scratchDir, eventScreens)

    screenName = projectName + "_screens"

    arcpy.management.CreateTable(geologyLoc, screenName)
    # Add fields to the new table
    tableScr = os.path.join(geologyLoc, screenName)
    arcpy.management.AddField(tableScr, "WELLID", "TEXT", "", "", "12", "", "NULLABLE", "NON_REQUIRED", "")
    arcpy.management.AddField(tableScr, "SEQ_NUM", "DOUBLE", "", "", "", "", "NULLABLE", "NON_REQUIRED", "")
    arcpy.management.AddField(tableScr, "DEPTH_TOP", "DOUBLE", "", "", "", "", "NULLABLE", "NON_REQUIRED", "")
    arcpy.management.AddField(tableScr, "DEPTH_BOT", "DOUBLE", "", "", "", "", "NULLABLE", "NON_REQUIRED", "")
    arcpy.management.AddField(tableScr, "THICKNESS", "DOUBLE", "", "", "", "", "NULLABLE", "NON_REQUIRED", "")
    arcpy.management.AddField(tableScr, "STRAT", "TEXT", "", "", "255", "", "NULLABLE", "NON_REQUIRED", "")
except:
    AddMsgAndPrint("ERROR 034: Failed to create the screens table",2)
    raise SystemError

try:
    screenMapping = ""
    screenMapping = arcpy.FieldMappings()
    screenMapping.addTable(tableScr)
    appendFieldMappingInput(fieldMappings=screenMapping, oldTable=eventScreens, oldField="WELLID",
                            newField="WELLID", newFieldType="TEXT")
    appendFieldMappingInput(fieldMappings=screenMapping, oldTable=eventScreens, oldField="SCREEN_FRM",
                            newField="DEPTH_TOP", newFieldType="DOUBLE")
    appendFieldMappingInput(fieldMappings=screenMapping, oldTable=eventScreens, oldField="SCREEN_TO",
                            newField="DEPTH_BOT", newFieldType="DOUBLE")
    arcpy.management.Append(eventScreens, tableScr, "NO_TEST", screenMapping, "")
except:
    AddMsgAndPrint("ERROR 035: Failed to append event data to permanent data table",2)
    raise SystemError

try:
    arcpy.management.CalculateField(tableScr, "SEQ_NUM", 1, "PYTHON3", "")
    arcpy.management.CalculateField(tableScr, "THICKNESS", "!DEPTH_BOT! - !DEPTH_TOP!", "PYTHON3", "")
    arcpy.management.CalculateField(tableScr, "STRAT", "\"Screen\"", "PYTHON3", "")
except:
    AddMsgAndPrint("ERROR 036: Failed to format empty fields in {}".format(os.path.splitext(os.path.basename(tableScr))[0]),2)
    raise SystemError
try:
    arcpy.AddMessage("Adding tables and cleaning scratch geodatabase...")
    pm = prj.activeMap
    pm.addDataFromPath(tableScr)
    prj.save()
    arcpy.management.Delete([eventScreens,outScreen])
except:
    AddMsgAndPrint("ERROR 037: Failed to add tables and clean geodatabase for screens",2)
    raise SystemError

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("BEGIN CREATING GROUNDWATER RASTER SURFACES FOR THE AREA...")
if customRange == "true":
    try:
        if standard_OR_no == "Standard 2-5 Mile Project":
            try:
                allYears = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_AllYears")
                createGWLraster(points=gwlWW, outraster=allYears, boundary=buff5mile)
            except:
                arcpy.AddError("ERROR 038-1: Failed to create 'All Years' raster")
                raise SystemError
            try:
                dateInterval = []
                for i in range(0, dateRange.rowCount):
                    startDate = dateRange.getValue(i, 0)
                    endDate = dateRange.getValue(i, 1)
                    oldTime = datetime.datetime.strptime(startDate, '%m/%d/%Y')
                    newTime = datetime.datetime.strptime(endDate, '%m/%d/%Y')
                    beginningYear = int(oldTime.year)
                    endingYear = int(newTime.year)

                    # Create a generic date object. The values are not important, just that the object is created to replace with
                    # the beginning year
                    genDate = datetime.datetime(year=1900, month=1, day=1)
                    date1 = genDate.replace(year=beginningYear).strftime('%Y-%m-%d %H:%M:%S')
                    date2 = genDate.replace(year=endingYear).strftime('%Y-%m-%d %H:%M:%S')
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
                                                     secondYear - 1))
                    selectWells = arcpy.management.SelectLayerByAttribute(
                        in_layer_or_view=gwlWW,
                        selection_type="NEW_SELECTION",
                        where_clause="CONST_DATE >= timestamp '{}' And CONST_DATE < timestamp '{}'".format(date[0],
                                                                                                           date[1]),
                        invert_where_clause=None)
                    createGWLraster(points=selectWells,
                                    outraster=rasterProject,
                                    boundary=buff5mile)
            except:
                arcpy.AddError("ERROR 038-2: Failed to create other custom time range rasters")
                raise SystemError
        if standard_OR_no == "Non-Standard Project Area":
            try:
                allYears = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_AllYears")
                createGWLraster(points=gwlWW, outraster=allYears, boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-1: Failed to create 'All Years' raster")
                raise SystemError
            try:
                dateInterval = []
                for i in range(0, dateRange.rowCount):
                    startDate = dateRange.getValue(i, 0)
                    endDate = dateRange.getValue(i, 1)
                    oldTime = datetime.datetime.strptime(startDate, '%m/%d/%Y')
                    newTime = datetime.datetime.strptime(endDate, '%m/%d/%Y')
                    beginningYear = int(oldTime.year)
                    endingYear = int(newTime.year)

                    # Create a generic date object. The values are not important, just that the object is created to replace with
                    # the beginning year
                    genDate = datetime.datetime(year=1900, month=1, day=1)
                    date1 = genDate.replace(year=beginningYear).strftime('%Y-%m-%d %H:%M:%S')
                    date2 = genDate.replace(year=endingYear).strftime('%Y-%m-%d %H:%M:%S')
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
                                                     secondYear - 1))
                    selectWells = arcpy.management.SelectLayerByAttribute(
                        in_layer_or_view=gwlWW,
                        selection_type="NEW_SELECTION",
                        where_clause="CONST_DATE >= timestamp '{}' And CONST_DATE < timestamp '{}'".format(date[0],
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
        if standard_OR_no == "Standard 2-5 Mile Project":
            try:
                allYears = os.path.join(locRaster, os.path.splitext(os.path.basename(gwlWW))[0] + "_AllYears")
                createGWLraster(points=gwlWW, outraster=allYears, boundary=buff5mile)
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
                createGWLraster(points=selctPre2000s,outraster=pre2000s,boundary=buff5mile)
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
                    date1 = genDate.replace(year=year1).strftime('%Y-%m-%d %H:%M:%S')
                    date2 = genDate.replace(year=year2).strftime('%Y-%m-%d %H:%M:%S')
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
                                                     secondYear - 1))
                    selectWells = arcpy.management.SelectLayerByAttribute(
                        in_layer_or_view=gwlWW,
                        selection_type="NEW_SELECTION",
                        where_clause="CONST_DATE >= timestamp '{}' And CONST_DATE < timestamp '{}'".format(date[0],
                                                                                                         date[1]),
                        invert_where_clause=None)
                    createGWLraster(points=selectWells,outraster=rasterProject,boundary=buff5mile)
            except:
                arcpy.AddError("ERROR 038-2: Failed to create other custom time range rasters")
                raise SystemError
        if standard_OR_no == "Non-Standard Project Area":
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
                    date1 = genDate.replace(year=year1).strftime('%Y-%m-%d %H:%M:%S')
                    date2 = genDate.replace(year=year2).strftime('%Y-%m-%d %H:%M:%S')
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
                                                     secondYear - 1))
                    selectWells = arcpy.management.SelectLayerByAttribute(
                        in_layer_or_view=gwlWW,
                        selection_type="NEW_SELECTION",
                        where_clause="CONST_DATE >= timestamp '{}' And CONST_DATE < timestamp '{}'".format(date[0],
                                                                                                         date[1]),
                        invert_where_clause=None)
                    createGWLraster(points=selectWells, outraster=rasterProject, boundary=featExtent)
            except:
                arcpy.AddError("ERROR 038-2: Failed to create other custom time range rasters")
                raise SystemError
    except:
        arcpy.AddError("ERROR 038: Failed to create groundwater rasters")
        raise SystemError

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("BEGIN CREATING BEDROCK RASTER SURFACE FOR THE AREA...")
try:
    if standard_OR_no == "Standard 2-5 Mile Project":
        bdrkRaster = os.path.join(locRaster, os.path.splitext(os.path.basename(outWWpoints))[0] + "_BDRK_SURFACE")
        bdrkPoints = arcpy.management.SelectLayerByAttribute(gwlWW,"NEW_SELECTION","BDRK_ELEV > 0",None)
        createBDRKraster(points=bdrkPoints, outraster=bdrkRaster, boundary=buff5mile)
    if standard_OR_no == "Non-Standard Project Area":
        bdrkRaster = os.path.join(locRaster, os.path.splitext(os.path.basename(outWWpoints))[0] + "_BDRK_SURFACE")
        bdrkPoints = arcpy.management.SelectLayerByAttribute(gwlWW,"NEW_SELECTION","BDRK_ELEV > 0",None)
        createBDRKraster(points=bdrkPoints, outraster=bdrkRaster, boundary=featExtent)
except:
    arcpy.AddError("ERROR: 039: Failed to create the bedrock surface")
    raise SystemError

arcpy.AddMessage('***FINISHED CREATING DATASETS UTILIZING THE SCHEMA DETAILED BY THE MICHIGAN GEOLOGICAL SURVEY***')
arcpy.AddMessage('General Disclaimer: All data present is derived from the Wellogic database. Please take time to validate the '
                 'datasets for validity before performing for any sort of analysis')
