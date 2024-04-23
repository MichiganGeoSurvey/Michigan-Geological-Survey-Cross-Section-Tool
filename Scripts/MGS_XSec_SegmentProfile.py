"""
MGS_XSec_SegmentProfile.py
Description: ArcToolbox tool script to create a set of cross-sections defined by the end user.
             Specifically built for ArcGIS Pro software.
Requirements: python, ArcGIS Pro
Author: Matthew Bell, Michigan Geological Survey, matthew.e.bell@wmich.edu
Date: 5/25/2023

Last updated: 4/23/2024
"""

# Import Modules
# *******************************************************
import os
import sys
import traceback
import arcpy
import re
import datetime
import math

# Functions
# *******************************************************
def checkExtensions():
    #Checking for the 3D Analyst extension
    try:
        if arcpy.CheckExtension("3D") == "Available":
            arcpy.CheckOutExtension("3D")
        else:
            raise "LicenseError"
        if arcpy.CheckExtension("LocationReferencing") == "Available":
            arcpy.CheckOutExtension("LocationReferencing")
        else:
            raise "LicenseError"
    except "LicenseError":
        arcpy.AddMessage("3D Analyst extension is unavailable")
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

def testAndDelete(fc):
    if arcpy.Exists(fc):
        arcpy.management.Delete(fc)

def unique_values(table, field):
    with arcpy.da.SearchCursor(table, field) as cursor:
        return sorted({row[0] for row in cursor})
    del row, cursor

def getCPValue(quadrant):
    cpDict = {"Northwest":"UPPER_LEFT", "Southwest":"LOWER_LEFT", "Northeast":"UPPER_RIGHT", "Southeast":"LOWER_RIGHT"}
    return cpDict[quadrant]

def fieldNone(fc, field):
    try:
        with arcpy.da.SearchCursor(fc, field) as rows:
            if rows.next()[0] in [None, ""]:
                return False
            else:
                return True
    except:
        return False

def placeEvents(inRoutes, idRteFld, eventTable, eventRteFld, fromVar, toVar, eventLay):
    props = "{} LINE {} {}".format(eventRteFld, fromVar, toVar)
    arcpy.lr.MakeRouteEventLayer(inRoutes, idRteFld, eventTable, props, "layer")
    arcpy.management.CopyFeatures("layer", "layer2")
    arcpy.management.MakeFeatureLayer("layer2", "layer3", "Shape_Length <> 0")
    arcpy.management.CopyFeatures("layer3", eventLay)
    descEvent = arcpy.ListFields(eventLay)
    if "WELLID" in descEvent:
        arcpy.management.DeleteIdentical(eventLay, "WELLID")
    else:
        pass

def plan2side(ZMLines, ve):
    rows = arcpy.UpdateCursor(ZMLines)
    n = 0
    for row in rows:
        feat = row.shape
        newFeatShape = arcpy.Array()
        a = 0
        while a < feat.partCount:
            newArray = feat.getPart(a)
            newShapeArray = arcpy.Array()
            pntOld = newArray.next()
            while pntOld:
                pntOld.X = float(pntOld.M) + float(moveLength)
                if elevUnits == "Meters":
                    pntOld.Y = float(pntOld.Z) * float(ve)
                if elevUnits == "Feet":
                    pntOld.Y = (float(pntOld.Z) * 0.3048) * float(ve)
                newShapeArray.add(pntOld)
                pntOld = newArray.next()
            newFeatShape.add(newShapeArray)
            a = a + 1
        row.shape = newFeatShape
        rows.updateRow(row)

def limitString(string,limit):
    if len(string) > limit:
        return string[0:limit]
    else:
        return string
# Parameters
# *******************************************************
# Output Geodatabase
outGDB = arcpy.GetParameterAsText(0)

# Cross-Section Lines
lineLayer = arcpy.GetParameterAsText(1)

# Elevation Units for project
elevUnits = arcpy.GetParameterAsText(2)

# Bedrock Surface
bdrkDEM = arcpy.GetParameterAsText(3)

# Groundwater Surface
gwlDEM = arcpy.ValueTable(3)
gwlDEM.loadFromString(arcpy.GetParameterAsText(4))

# Borehole Points
bhPoints = arcpy.GetParameterAsText(5)

# Selection Distance
buff = arcpy.GetParameterAsText(6)

# Vertical Exaggeration
ve = arcpy.GetParameterAsText(7)

# Local Variables
# *******************************************************
checkExtensions()
# Let's create the unknown spatial reference for the output files
wkt = 'PROJCS["Cross-Section Coordinate System",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Local"],PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],PARAMETER["Scale_Factor",1.0],PARAMETER["Azimuth",45.0],PARAMETER["Longitude_Of_Center",-75.0],PARAMETER["Latitude_Of_Center",40.0],UNIT["Meter",1.0]];-6386900 -6357100 10000;-100000 10000;-100000 10000;0.001;0.001;0.001;IsHighPrecision'
unknown = arcpy.SpatialReference(text=wkt)

# Begin
# *******************************************************
# Environment Variables
arcpy.env.overwriteOutput = True
arcpy.env.transferDomains = True
prj = arcpy.mp.ArcGISProject("CURRENT")
scratchDir = prj.defaultGeodatabase
AddMsgAndPrint(msg="Scratch Geodatabase: {}".format(os.path.basename(scratchDir)),
               severity=0)

# Defining the list of cross-section names for the creation process
allValue = unique_values(lineLayer, "XSEC")

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("BEGIN BEDROCK SURFACE CREATION")
if bdrkDEM == "":
    AddMsgAndPrint("- No bedrock surface defined, passing to next step...")
    pass
else:
    featExtent = os.path.join(scratchDir, "ProjectAreaExtent_BDRK")
    testAndDelete(featExtent)
    arcpy.ddd.RasterDomain(bdrkDEM, featExtent, "POLYGON")
    for Value in allValue:
        try:
            arcpy.AddMessage("*Analyzing {}...*".format(Value))
            arcpy.management.MakeFeatureLayer(lineLayer, "lineLayers")
            arcpy.management.SelectLayerByAttribute("lineLayers", "NEW_SELECTION", "{}='{}'".format('XSEC', Value))

            xs_name = "{}_{}".format(os.path.basename(lineLayer), Value)
            tempFields = [f.name for f in arcpy.ListFields("lineLayers")]
            checkField = "{}_ID".format(xs_name)
            idField = next((f for f in tempFields if f == checkField), None)
            idExists = fieldNone("lineLayers", checkField)

            if idField is None or idExists == False:
                idField = "ROUTEID"
                arcpy.management.AddField("lineLayers", idField, "TEXT")
                arcpy.management.CalculateField("lineLayers", checkField, "'01'", "PYTHON3")

            desc = arcpy.da.Describe(lineLayer)
            hasZ = desc["hasZ"]
            hasM = desc["hasM"]

            if hasZ and hasM:
                zm_line = "lineLayers"
                AddMsgAndPrint(
                    "*Cross-section {} in {} already has M and Z values".format(Value, os.path.basename(lineLayer)))
            else:
                # Add z values
                z_line = os.path.join(scratchDir, "XSEC_{}_z".format(Value))
                arcpy.ddd.InterpolateShape(bdrkDEM, "lineLayers", z_line)
                arcpy.management.AddField(z_line, "QUAD", "TEXT", "", "", "255", "", "NULLABLE")
                with arcpy.da.UpdateCursor(z_line, ["DIRECTION", "QUAD"]) as cursor:
                    for row in cursor:
                        if (row[0] == "W-E" or row[0] == "NW-SE" or row[0] == "E-W"):
                            quad = "Northwest"
                            row[1] = quad
                            arcpy.AddMessage("- Analyzing from NW quad")
                        if (row[0] == "SW-NE" or row[0] == "S-N" or row[0] == "N-S"):
                            quad = "Southwest"
                            row[1] = quad
                            arcpy.AddMessage("- Analyzing from SW quad")
                        if row[0] == "NE-SW":
                            quad = "Northeast"
                            row[1] = quad
                            arcpy.AddMessage("- Analyzing from NE quad")
                        if row[0] == "SE-NW":
                            quad = "Southeast"
                            row[1] = quad
                            arcpy.AddMessage("- Analyzing from SE quad")
                        else:
                            pass
                        cursor.updateRow(row)
                del row, cursor
                cpDir = arcpy.SearchCursor(z_line, "", "", "", "QUAD D").next().getValue("QUAD")
                cp = getCPValue(cpDir)
                zm_line = os.path.join(scratchDir, "XSEC_{}_zm".format(Value))
                arcpy.lr.CreateRoutes(z_line, checkField, zm_line, "LENGTH", "#", "#", cp)

                # Now we need to determine if the profile starts after the beginning of the line.
                # Step 1: Erase the temporary feature layer to exclude the area inside the raster area...
                eraseFeat = os.path.join(scratchDir,"BDRK_ERASE")
                testAndDelete(eraseFeat)
                arcpy.analysis.Erase(
                    in_features="lineLayers",
                    erase_features=featExtent,
                    out_feature_class=eraseFeat,
                    cluster_tolerance=None
                )
                singleFeat = os.path.join(scratchDir,"BDRK_ERASE_SINGLE")
                testAndDelete(singleFeat)
                arcpy.management.MultipartToSinglepart(
                    in_features=eraseFeat,
                    out_feature_class=singleFeat
                )
                # Step 2: Get the extent of the lines to see if the profile has been offset...
                profileAlign = arcpy.Describe(zm_line)
                mainLineAlign = arcpy.Describe("lineLayers")
                geometries = arcpy.management.CopyFeatures(singleFeat,arcpy.Geometry())
                moveLength = 0
                for geometry in geometries:
                    if (cpDir == "Northwest" or cpDir == "Southwest"):
                        if (profileAlign.extent.XMin > mainLineAlign.extent.XMin and geometry.extent.XMin == mainLineAlign.extent.XMin):
                            moveLength += float(geometry.length)
                            AddMsgAndPrint(moveLength)
                        else:
                            pass
                    else:
                        AddMsgAndPrint(cpDir)
                        if (profileAlign.extent.XMax < mainLineAlign.extent.XMax and geometry.extent.XMax == mainLineAlign.extent.XMax):
                            moveLength += float(geometry.length)
                            AddMsgAndPrint(moveLength)
                        else:
                            pass
        except:
            AddMsgAndPrint("ERROR 009: Failed to create bedrock surface for {}".format(Value), 2)
            raise SystemError
        try:
            AddMsgAndPrint("    Creating the confidence zone polygon feature class...")
            bdrkpoints = arcpy.management.SelectLayerByAttribute(
                in_layer_or_view=bhPoints,
                selection_type="NEW_SELECTION",
                where_clause="DEPTH_2_BDRK > 0",
                invert_where_clause=None)
            bdrkBuff = os.path.join(scratchDir,"XSEC_{}_BUFF_BDRK_{}{}".format(Value,buff.split(" ")[0],buff.split(" ")[1]))
            arcpy.analysis.Buffer(bdrkpoints, bdrkBuff, buff, "FULL", "ROUND", "ALL", None, "PLANAR")

            arcpy.management.CreateFeatureclass(scratchDir, "ProjectAreaExtent", "POLYGON")

            unionBDRK = os.path.join(scratchDir, "XSEC_{}_UNION_BDRK".format(Value))
            inFeatures = [featExtent, bdrkBuff]
            arcpy.analysis.Union(inFeatures, unionBDRK, "ONLY_FID", None, "GAPS")
            bdrkConfidence = os.path.join(os.path.dirname(bhPoints), "XSEC_{}_BDRK_ConZone".format(Value))
            arcpy.management.CopyFeatures(unionBDRK,bdrkConfidence)
            arcpy.management.AddField(
                in_table=bdrkConfidence,
                field_name="CONFIDENCE",
                field_type="TEXT",
                field_length="255",
                field_is_nullable="NULLABLE",
                field_is_required="NON_REQUIRED",
                field_domain="CONFIDENCE")
            with arcpy.da.UpdateCursor(bdrkConfidence, ["FID_{}".format(limitString(os.path.basename(featExtent),60)),
                                                        "FID_{}".format(limitString(os.path.basename(bdrkBuff),60)),
                                                        "CONFIDENCE"]) as cursor:
                for row in cursor:
                    if row[0] == -1:
                        cursor.deleteRow()
                    if (row[0] == 1 and row[1] == -1):
                        row[2] = "INFERRED"
                        cursor.updateRow(row)
                    if (row[0] == 1 and row[1] == 1):
                        row[2] = "CONFIDENT"
                        cursor.updateRow(row)
                del row, cursor
        except:
            AddMsgAndPrint("ERROR 010: Failed to create confidence zone for {}".format(os.path.basename(bdrkDEM)),2)
            raise SystemError
        try:
            AddMsgAndPrint("    Create segmented profile for bedrock profile...")
            conEventsTable = os.path.join(scratchDir, "{}_polyEvents_{}".format(os.path.basename(bdrkConfidence),Value))
            testAndDelete(conEventsTable)
            conProps = "rkey LINE FromM ToM"
            arcpy.lr.LocateFeaturesAlongRoutes(bdrkConfidence, zm_line, checkField, "#", conEventsTable, conProps,
                                               "FIRST", "NO_DISTANCE", "NO_ZERO")
            locatedEvents_bdrk = os.path.join(scratchDir, "{}_located_{}".format(os.path.basename(bdrkConfidence),Value))
            conEvent_sort = os.path.join(scratchDir,
                                         "{}_polyEvents_{}_sorted".format(os.path.basename(bdrkConfidence), Value))
            arcpy.management.Sort(in_dataset=conEventsTable, out_dataset=conEvent_sort,
                                  sort_field=[["FromM", "ASCENDING"]])
            placeEvents(inRoutes=zm_line,
                        idRteFld=checkField,
                        eventTable=conEvent_sort,
                        eventRteFld="rkey",
                        fromVar="FromM",
                        toVar="ToM",
                        eventLay=locatedEvents_bdrk)

            bdrkProfile = os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)), "XSEC_{}_BDRK_{}x".format(Value, ve))
            arcpy.management.CreateFeatureclass(os.path.join(outGDB,"XSEC_{}".format(Value)),
                                                os.path.basename(bdrkProfile), "POLYLINE", locatedEvents_bdrk,
                                                "ENABLED", "ENABLED")
            arcpy.management.Append(locatedEvents_bdrk, bdrkProfile, "NO_TEST")
            plan2side(ZMLines=bdrkProfile, ve=ve)
        except:
            AddMsgAndPrint("ERROR 011: Failed to segment the bedrock profile.",2)
            raise SystemError
        try:
            AddMsgAndPrint("    Cleaning {}...".format(os.path.basename(scratchDir)))
            xsecMap = prj.listMaps('XSEC_{}'.format(Value))[0]
            xsecMap.addDataFromPath(bdrkProfile)
            arcpy.management.SelectLayerByAttribute("lineLayers", "CLEAR_SELECTION")
            arcpy.management.SelectLayerByAttribute(bhPoints, "CLEAR_SELECTION")
            arcpy.management.Delete([bdrkBuff,unionBDRK,eraseFeat,singleFeat,bdrkConfidence])
            arcpy.management.DeleteField(lineLayer,checkField)

            bdrkLayer = xsecMap.listLayers(os.path.splitext(os.path.basename(bdrkProfile))[0])[0]

            # Grids symbology...
            symBDRK = bdrkLayer.symbology
            symBDRK.updateRenderer("UniqueValueRenderer")
            bdrkLayer.symbology = symBDRK

            symBDRK.renderer.fields = ["CONFIDENCE"]
            symBDRK.renderer.removeValues({"CONFIDENCE": ["CONFIDENT", "INFERRED"]})
            bdrkLayer.symbology = symBDRK
            symBDRK.renderer.addValues({"Confidence of Profile": ["CONFIDENT", "INFERRED"]})
            bdrkLayer.symbology = symBDRK
            for group in symBDRK.renderer.groups:
                for item in group.items:
                    if item.values[0][0] == "CONFIDENT":
                        item.symbol.outlineColor = {'RGB': [0, 0, 0, 100]}
                        item.symbol.outlineWidth = 1
                        item.label = "Confident Surface"
                        bdrkLayer.symbology = symBDRK
                    elif item.values[0][0] == "INFERRED":
                        item.symbol.applySymbolFromGallery('Dashed 6:6')
                        item.symbol.outlineColor = {'RGB': [0, 0, 0, 100]}
                        item.symbol.outlineWidth = 1
                        item.label = "Inferred Surface"
                        bdrkLayer.symbology = symBDRK
            prj.save()
        except:
            AddMsgAndPrint("ERROR 012: Failed to clean up {}".format(os.path.basename(scratchDir)), 2)
            raise SystemError

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("BEGIN GROUNDWATER SURFACE CREATION")
if gwlDEM == "":
    AddMsgAndPrint("- Groundwater rasters not defined. Passing to grid creation...")
    pass
else:
    for Value in allValue:
        for i in range(0, gwlDEM.rowCount):
            raster = gwlDEM.getValue(i, 0)
            startYear = gwlDEM.getValue(i, 1)
            endYear = gwlDEM.getValue(i, 2)

            featExtent = os.path.join(scratchDir, "ProjectAreaExtent_{}".format(os.path.splitext(os.path.basename(raster))[0]))
            testAndDelete(featExtent)
            arcpy.ddd.RasterDomain(raster, featExtent, "POLYGON")
            try:
                arcpy.AddMessage("*Analyzing {} for {}...*".format(raster, Value))
                arcpy.management.MakeFeatureLayer(lineLayer, "lineLayers")
                arcpy.management.SelectLayerByAttribute("lineLayers", "NEW_SELECTION", "{}='{}'".format('XSEC', Value))

                xs_name = "{}_{}".format(os.path.basename(lineLayer), Value)
                tempFields = [f.name for f in arcpy.ListFields("lineLayers")]
                checkField = "{}_ID".format(xs_name)
                idField = next((f for f in tempFields if f == checkField), None)
                idExists = fieldNone("lineLayers", checkField)

                if idField is None or idExists == False:
                    idField = "ROUTEID"
                    arcpy.management.AddField("lineLayers", idField, "TEXT")
                    arcpy.management.CalculateField("lineLayers", checkField, "'01'", "PYTHON3")

                desc = arcpy.da.Describe(lineLayer)
                hasZ = desc["hasZ"]
                hasM = desc["hasM"]

                if hasZ and hasM:
                    zm_line = "lineLayers"
                    AddMsgAndPrint(
                        "*Cross-section {} in {} already has M and Z values".format(Value, os.path.basename(lineLayer)))
                else:
                    # Add z values
                    z_line = os.path.join(scratchDir, "XSEC_{}_z".format(Value))
                    arcpy.ddd.InterpolateShape(raster, "lineLayers", z_line)
                    arcpy.management.AddField(z_line, "QUAD", "TEXT", "", "", "255", "", "NULLABLE")
                    with arcpy.da.UpdateCursor(z_line, ["DIRECTION", "QUAD"]) as cursor:
                        for row in cursor:
                            if (row[0] == "W-E" or row[0] == "NW-SE" or row[0] == "E-W"):
                                quad = "Northwest"
                                row[1] = quad
                                arcpy.AddMessage("- Analyzing from NW quad")
                            if (row[0] == "SW-NE" or row[0] == "S-N" or row[0] == "N-S"):
                                quad = "Southwest"
                                row[1] = quad
                                arcpy.AddMessage("- Analyzing from SW quad")
                            if row[0] == "NE-SW":
                                quad = "Northeast"
                                row[1] = quad
                                arcpy.AddMessage("- Analyzing from NE quad")
                            if row[0] == "SE-NW":
                                quad = "Southeast"
                                row[1] = quad
                                arcpy.AddMessage("- Analyzing from SE quad")
                            else:
                                pass
                            cursor.updateRow(row)
                        del row
                        del cursor
                    cpDir = arcpy.SearchCursor(z_line, "", "", "", "QUAD D").next().getValue("QUAD")
                    cp = getCPValue(cpDir)
                    zm_line = os.path.join(scratchDir, "XSEC_{}_zm".format(Value))
                    arcpy.lr.CreateRoutes(z_line, checkField, zm_line, "LENGTH", "#", "#", cp)

                    # Now we need to determine if the profile starts after the beginning of the line.
                    # Step 1: Erase the temporary feature layer to exclude the area inside the raster area...
                    eraseFeat = os.path.join(scratchDir, "GWL_ERASE")
                    testAndDelete(eraseFeat)
                    arcpy.analysis.Erase(
                        in_features="lineLayers",
                        erase_features=featExtent,
                        out_feature_class=eraseFeat,
                        cluster_tolerance=None
                    )
                    singleFeat = os.path.join(scratchDir, "GWL_ERASE_SINGLE")
                    testAndDelete(singleFeat)
                    arcpy.management.MultipartToSinglepart(
                        in_features=eraseFeat,
                        out_feature_class=singleFeat
                    )
                    # Step 2: Get the extent of the lines to see if the profile has been offset...
                    profileAlign = arcpy.Describe(zm_line)
                    mainLineAlign = arcpy.Describe("lineLayers")
                    geometries = arcpy.management.CopyFeatures(singleFeat, arcpy.Geometry())
                    moveLength = 0
                    for geometry in geometries:
                        if (cpDir == "Northwest" or cpDir == "Southwest"):
                            if (profileAlign.extent.XMin > mainLineAlign.extent.XMin or geometry.extent.XMin == mainLineAlign.extent.XMin):
                                moveLength += float(geometry.length)
                            else:
                                pass
                        else:
                            AddMsgAndPrint(cpDir)
                            if (profileAlign.extent.XMax < mainLineAlign.extent.XMax or geometry.extent.XMax == mainLineAlign.extent.XMax):
                                moveLength += float(geometry.length)
                            else:
                                pass
            except:
                AddMsgAndPrint("ERROR 013: Failed to create {} for XSEC {}".format(raster, Value), 2)
                raise SystemError

            try:
                if (startYear == "All Years" or endYear == "All Years" or (startYear == "" and endYear == "")):
                    AddMsgAndPrint("    Creating the confidence zone polygon feature class...")
                    buffWW = os.path.basename(bhPoints) + "_{}{}_buff_AllYears".format(buff.split(" ")[0],buff.split(" ")[1])
                    arcpy.analysis.Buffer(bhPoints, buffWW, "{}".format(buff), "FULL", "ROUND", "ALL", None, "PLANAR")
                    unionWW = os.path.basename(bhPoints) + "_Union"
                    inFeatures = [featExtent, buffWW]
                    arcpy.analysis.Union(inFeatures, unionWW, 'ONLY_FID', None, 'GAPS')
                    confidenceZone = os.path.join(scratchDir, os.path.basename(raster) + "_CONFIDENCE_ZONE")
                    arcpy.management.CopyFeatures(unionWW, confidenceZone)
                    arcpy.management.SelectLayerByAttribute(unionWW, "CLEAR_SELECTION")
                    arcpy.management.AddField(
                        in_table=confidenceZone,
                        field_name="CONFIDENCE",
                        field_type="TEXT",
                        field_length="255",
                        field_is_nullable="NULLABLE",
                        field_is_required="NON_REQUIRED",
                        field_domain="CONFIDENCE")
                    with arcpy.da.UpdateCursor(confidenceZone,
                                               ["FID_{}".format(limitString(os.path.splitext(os.path.basename(featExtent))[0],60)),
                                                "FID_{}".format(limitString(os.path.splitext(os.path.basename(buffWW))[0],60)),
                                                "CONFIDENCE"]) as cursor:
                        for row in cursor:
                            if row[0] == -1:
                                cursor.deleteRow()
                            if (row[0] == 1 and row[1] == -1):
                                row[2] = "INFERRED"
                                cursor.updateRow(row)
                            if (row[0] == 1 and row[1] == 1):
                                row[2] = "CONFIDENT"
                                cursor.updateRow(row)
                        del row, cursor

                else:
                    AddMsgAndPrint("    Creating the confidence zone polygon feature class...")
                    yearRangeRaster = arcpy.management.SelectLayerByAttribute(
                        in_layer_or_view=bhPoints,
                        selection_type="NEW_SELECTION",
                        where_clause="CONST_DATE >= timestamp '{}-01-01 00:00:00' And CONST_DATE <= timestamp '{}-12-31 00:00:00'".format(startYear,endYear),
                        invert_where_clause=None)
                    buffWW = os.path.basename(bhPoints) + "_{}{}_buff_{}_{}".format(buff.split(" ")[0],
                                                                                   buff.split(" ")[1],
                                                                                    startYear,
                                                                                    endYear)
                    arcpy.analysis.Buffer(yearRangeRaster, buffWW, "{}".format(buff), "FULL", "ROUND", "ALL", None,
                                          "PLANAR")
                    unionWW = os.path.basename(bhPoints) + "_Union"
                    inFeatures = [featExtent, buffWW]
                    arcpy.analysis.Union(inFeatures, unionWW, 'ONLY_FID', None, 'GAPS')
                    confidenceZone = os.path.join(scratchDir, os.path.basename(raster) + "_CONFIDENCE_ZONE")
                    arcpy.management.CopyFeatures(unionWW, confidenceZone)
                    arcpy.management.SelectLayerByAttribute(unionWW, "CLEAR_SELECTION")
                    arcpy.management.AddField(
                        in_table=confidenceZone,
                        field_name="CONFIDENCE",
                        field_type="TEXT",
                        field_length="255",
                        field_is_nullable="NULLABLE",
                        field_is_required="NON_REQUIRED",
                        field_domain="CONFIDENCE")
                    with arcpy.da.UpdateCursor(confidenceZone,
                                               ["FID_{}".format(limitString(os.path.splitext(os.path.basename(featExtent))[0],60)),
                                                "FID_{}".format(limitString(os.path.splitext(os.path.basename(buffWW))[0],60)),
                                                "CONFIDENCE"]) as cursor:
                        for row in cursor:
                            if row[0] == -1:
                                cursor.deleteRow()
                            if (row[0] == 1 and row[1] == -1):
                                row[2] = "INFERRED"
                                cursor.updateRow(row)
                            if (row[0] == 1 and row[1] == 1):
                                row[2] = "CONFIDENT"
                                cursor.updateRow(row)
                        del row, cursor
            except:
                AddMsgAndPrint("ERROR 014: Failed to create confidence zone for {}".format(os.path.basename(raster)),
                               2)
                raise SystemError
            try:
                AddMsgAndPrint("    Create segmented profile for {} profile...".format(os.path.basename(raster)))
                conEventsTable = os.path.join(scratchDir,
                                              "{}_polyEvents_{}".format(os.path.basename(confidenceZone), Value))
                conProps = "rkey LINE FromM ToM"
                arcpy.lr.LocateFeaturesAlongRoutes(confidenceZone, zm_line, checkField, "#", conEventsTable, conProps,
                                                   "FIRST", "NO_DISTANCE", "NO_ZERO")
                locatedEvents_gwl = os.path.join(scratchDir,
                                                  "{}_located_{}".format(os.path.basename(confidenceZone), Value))
                placeEvents(inRoutes=zm_line,
                            idRteFld=checkField,
                            eventTable=conEventsTable,
                            eventRteFld="rkey",
                            fromVar="FromM",
                            toVar="ToM",
                            eventLay=locatedEvents_gwl)
                if (startYear == "All Years" or endYear == "All Years" or (startYear == "" and endYear == "")):
                    gwlProfile = os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)), "XSEC_{}_GWL_AllYears_{}x".format(Value, ve))
                else:
                    gwlProfile = os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)), "XSEC_{}_GWL_{}_{}_{}x".format(Value,startYear,endYear, ve))
                arcpy.management.CreateFeatureclass(os.path.join(outGDB, "XSEC_{}".format(Value)),
                                                    os.path.basename(gwlProfile), "POLYLINE", locatedEvents_gwl,
                                                    "ENABLED", "ENABLED")
                arcpy.management.Append(locatedEvents_gwl, gwlProfile, "NO_TEST")
                plan2side(ZMLines=gwlProfile, ve=ve)
            except:
                AddMsgAndPrint("ERROR 015: Failed to segment the groundwater profile.", 2)
                raise SystemError

            try:
                AddMsgAndPrint("    Cleaning {}...".format(os.path.basename(scratchDir)))
                xsecMap = prj.listMaps('XSEC_{}'.format(Value))[0]
                xsecMap.addDataFromPath(gwlProfile)
                arcpy.management.SelectLayerByAttribute("lineLayers", "CLEAR_SELECTION")
                arcpy.management.SelectLayerByAttribute(bhPoints, "CLEAR_SELECTION")
                arcpy.management.Delete([zm_line,buffWW,unionWW,confidenceZone,singleFeat,eraseFeat])
                arcpy.management.DeleteField(lineLayer, checkField)

                gwlLayer = xsecMap.listLayers(os.path.splitext(os.path.basename(gwlProfile))[0])[0]

                # Grids symbology...
                symGWL = gwlLayer.symbology
                symGWL.updateRenderer("UniqueValueRenderer")
                gwlLayer.symbology = symGWL

                symGWL.renderer.fields = ["CONFIDENCE"]
                symGWL.renderer.removeValues({"CONFIDENCE": ["CONFIDENT", "INFERRED"]})
                gwlLayer.symbology = symGWL
                symGWL.renderer.addValues({"Confidence of Profile": ["CONFIDENT", "INFERRED"]})
                gwlLayer.symbology = symGWL
                for group in symGWL.renderer.groups:
                    for item in group.items:
                        if item.values[0][0] == "CONFIDENT":
                            item.symbol.outlineColor = {'RGB': [0, 197, 255, 100]}
                            item.symbol.outlineWidth = 1
                            item.label = "Confident Surface"
                            gwlLayer.symbology = symGWL
                        elif item.values[0][0] == "INFERRED":
                            item.symbol.applySymbolFromGallery('Dashed 6:6')
                            item.symbol.outlineColor = {'RGB': [0, 197, 255, 100]}
                            item.symbol.outlineWidth = 1
                            item.label = "Inferred Surface"
                            gwlLayer.symbology = symGWL
                prj.save()
                AddMsgAndPrint("PLease make sure to change color symbology for different groundwater intervals.")
            except:
                AddMsgAndPrint("ERROR 016: Failed to clean up {}".format(os.path.basename(scratchDir)), 2)
                raise SystemError