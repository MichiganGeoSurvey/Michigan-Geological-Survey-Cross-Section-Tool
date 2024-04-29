"""
MGS_XSec_AllSteps.py
Description: ArcToolbox tool script to create a set of cross-sections defined by the end user.
             Specifically built for ArcGIS Pro software.
Requirements: python, ArcGIS Pro
Author: Matthew Bell, Michigan Geological Survey, matthew.e.bell@wmich.edu
Date: 5/25/2023

Last updated: 5/25/2023
"""

# Import Modules
# *******************************************************
import os
import sys
import traceback
import arcpy
import re
from datetime import datetime, timedelta
import math
import numpy as np
import time
import threading

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

def round2int(x,base):
    return base * round(x/base)

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

def removeBasemaps(map):
    try:
        basenameLayer = map.listLayers('World Topographic Map')[0]
        hillLayer = map.listLayers('World Hillshade')[0]
        map.removeLayer(basenameLayer)
        map.removeLayer(hillLayer)
    except:
        arcpy.AddMessage('  *Basemap already removed. Passing to next step...')
        pass

def add_id(out_name, field_names, out_path):
    id_name = "{}_id".format(out_name)
    if not id_name in field_names:
        arcpy.management.AddField(out_path, id_name, "TEXT",field_length=50)
    letters = []
    for s in out_name:
        if s.isalpha():
            if s.isupper():
                letters.append(s)
    pref = "".join(letters)
    return id_name, pref

def cartesianToGeographic(angle):
    ctg = -90 - angle
    if ctg < 0:
        ctg = ctg + 360
        return ctg

def locateEvents_Table(pts, sel_dist, event_props, z_type, is_lines=False):
    desc = arcpy.da.Describe(pts)
    if not desc["hasZ"]:
        arcpy.ddd.AddSurfacInformation(pts, dem, z_type, "LINEAR")

    dupDetectField = "xDupDetect"
    arcpy.management.AddField(pts, dupDetectField, "LONG")
    eventLocTable = os.path.join(scratchDir, "XSEC_{}_bhEvents".format(Value))
    testAndDelete(eventLocTable)
    arcpy.lr.LocateFeaturesAlongRoutes(pts,zm_line,checkField,sel_dist,eventLocTable,event_props)
    nRows = int(arcpy.GetCount_management(eventLocTable)[0])
    nPts = int(arcpy.GetCount_management(pts)[0])
    if nRows > nPts and not is_lines:
        arcpy.management.DeleteIdentical(eventLocTable, dupDetectField)
    arcpy.management.DeleteField(eventLocTable, dupDetectField)
    return eventLocTable

def boreholes(locatedPoints):
    bhLinesName = "XSEC_{}_bhLines".format(Value)
    bhSticks = os.path.join(scratchDir, bhLinesName)
    arcpy.management.CreateFeatureclass(scratchDir, bhLinesName, "POLYLINE", locatedPoints, "DISABLED",
                                        "SAME_AS_TEMPLATE")

    lf = arcpy.ListFields(locatedPoints)
    bhFields = [f.name for f in lf if f.type != "Geometry"]
    bhFields.append("SHAPE@")

    uniq_ID, id_pref = add_id(bhLinesName, bhFields, bhSticks)

    tRows = arcpy.da.SearchCursor(locatedPoints, bhFields)
    bhFields.append(uniq_ID)
    cur = arcpy.da.InsertCursor(bhSticks, bhFields)
    oidName = [f.name for f in lf if f.type == "OID"][0]
    oid_i = tRows.fields.index(oidName)
    elevID = tRows.fields.index(zField)
    depthID = tRows.fields.index("BOREH_DEPTH")

    i = 0
    for row in tRows:
        if elevUnits == "Meters":
            i = i + 1
            geom = row[-1]
            existPnt = geom[0]
            bhArray = []
            X = existPnt.M
            Ytop = float(row[elevID])
            Ybot = Ytop - float(row[depthID])
            bhArray.append((X, Ytop * float(ve)))
            bhArray.append((X, Ybot * float(ve)))
            vals = list(row).copy()
            vals.append("")
            vals[-2] = bhArray
            csAzi = cartesianToGeographic(angle=row[tRows.fields.index("LOC_ANGLE")])
            vals[tRows.fields.index("LocalXSEC_Azimuth")] = csAzi
            vals[tRows.fields.index("DistFromSection")] = row[tRows.fields.index("Distance")]
            vals[-1] = "{}{}".format(id_pref, i)
            try:
                cur.insertRow(vals)
                bhArray.clear()
            except Exception as e:
                AddMsgAndPrint("Could not create feature from objectid {} in {}".format(row[oid_i], locPoints), 1)
                AddMsgAndPrint(e)
        if elevUnits == "Feet":
            i = i + 1
            geom = row[-1]
            existPnt = geom[0]
            bhArray = []
            X = existPnt.M
            Ytop = float(row[elevID]) * 0.3048
            Ybot = Ytop - (float(row[depthID]) * 0.3048)
            bhArray.append((X, Ytop * float(ve)))
            bhArray.append((X, Ybot * float(ve)))
            vals = list(row).copy()
            vals.append("")
            vals[-2] = bhArray
            csAzi = cartesianToGeographic(angle=row[tRows.fields.index("LOC_ANGLE")])
            vals[tRows.fields.index("LocalXSEC_Azimuth")] = csAzi
            vals[tRows.fields.index("DistFromSection")] = row[tRows.fields.index("Distance")]
            vals[-1] = "{}{}".format(id_pref, i)
            try:
                cur.insertRow(vals)
                bhArray.clear()
            except Exception as e:
                AddMsgAndPrint("Could not create feature from objectid {} in {}".format(row[oid_i],
                                                                                        os.path.basename(
                                                                                            locatedPoints)), 1)
                AddMsgAndPrint(e)
        del row
    del tRows, cur
    return bhSticks
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
# The process seems to have worked itself out and this may not be necessary (1/19/2024)
"""
class ExecutionTimeout(Exception): pass
    def start(max_duration = timedelta(seconds=3600)):
        local.start_time = datetime.now()
        local.max_duration = max_duration
    def check():
        if datetime.now() - local.start_time > local.max_duration:
            raise ExecutionTimeout()
    def do_work(input,output):
        start()
        while True:
            check()
        return 10
    try:
        do_work()
    except ExecutionTimeout:
        arcpy.AddMessage("Process timed out.")
        raise SystemError
"""

# Parameters
# *******************************************************
# Output Geodatabase
outGDB = arcpy.GetParameterAsText(0)

# Cross-Section Lines
lineLayer = arcpy.GetParameterAsText(1)

# Elevation Units for project
elevUnits = arcpy.GetParameterAsText(2)

# Surface Topography DEM
dem = arcpy.GetParameterAsText(3)

# Bedrock Surface
bdrkDEM = arcpy.GetParameterAsText(4)

# Groundwater Surface
gwlDEM = arcpy.ValueTable(3)
gwlDEM.loadFromString(arcpy.GetParameterAsText(5))

# Determine if the data is a custom dataset or from the MGS Data Reformatting Script
custom = arcpy.GetParameterAsText(6)

# Borehole Points
bhPoints = arcpy.GetParameterAsText(7)

# Borehole Points Fields
bhPointsFields = arcpy.ValueTable(4)
bhPointsFields.loadFromString(arcpy.GetParameterAsText(8))

# Lithology Table
lithTable = arcpy.GetParameterAsText(9)

# Lithology Table Fields
lithTableFields = arcpy.ValueTable(3)
lithTableFields.loadFromString(arcpy.GetParameterAsText(10))

# Screens Table
scrnTable = arcpy.GetParameterAsText(11)

# Screens Table Fields
scrnTableFields = arcpy.ValueTable(3)
scrnTableFields.loadFromString(arcpy.GetParameterAsText(12))

# Vertical Exaggeration
ve = arcpy.GetParameterAsText(13)

# Option for Polygon or Polyline
stickForm = arcpy.GetParameterAsText(14)

# Selection Distance
buff = arcpy.GetParameterAsText(15)

# Grid line spacing option
grids = arcpy.ValueTable(4)
grids.loadFromString(arcpy.GetParameterAsText(16))

# Symbologies for the different layers
symbols = arcpy.ValueTable(2)
symbols.loadFromString(arcpy.GetParameterAsText(17))

# Local Variables
# *******************************************************
checkExtensions()
# Let's create the unknown spatial reference for the output files
wkt = 'PROJCS["Cross-Section Coordinate System",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Local"],PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],PARAMETER["Scale_Factor",1.0],PARAMETER["Azimuth",45.0],PARAMETER["Longitude_Of_Center",-75.0],PARAMETER["Latitude_Of_Center",40.0],UNIT["Meter",1.0]];-6386900 -6357100 10000;-100000 10000;-100000 10000;0.001;0.001;0.001;IsHighPrecision'
unknown = arcpy.SpatialReference(text=wkt)

# Begin
# *******************************************************
# Environment Variables
local = threading.local()
arcpy.env.overwriteOutput = True
arcpy.env.transferDomains = True
prj = arcpy.mp.ArcGISProject("CURRENT")
scratchDir = prj.defaultGeodatabase
AddMsgAndPrint(msg="Scratch Geodatabase: {}".format(os.path.basename(scratchDir)),
               severity=0)

# Defining the list of cross-section names for the creation process
allValue = unique_values(lineLayer, "XSEC")

# Define the map project area and create the cross-section maps
mapList = []
for Value in allValue:
    mapName = "XSEC_"+Value
    mapList.append(mapName)
oldMaps = []
for map in prj.listMaps():
    oldMaps.append(map.name)
for m in mapList:
    if m in oldMaps:
        prj.deleteItem(prj.listMaps(m)[0])
        prj.createMap(m)
    else:
        prj.createMap(m)
for map in prj.listMaps("XSEC_*"):
    removeBasemaps(map)

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("CREATE DATASET FOR OUTPUTS")
# We need to implement any custom datasets into the mixture...
try:
    if custom == "true":
        newBhPoints = os.path.join(scratchDir, "{}_BH_MGS".format(os.path.splitext(os.path.basename(bhPoints))[0]))
        newLithTable = os.path.join(scratchDir, "{}_LITH_MGS".format(os.path.splitext(os.path.basename(lithTable))[0]))
        newScrnTable = os.path.join(scratchDir, "{}_SCRN_MGS".format(os.path.splitext(os.path.basename(scrnTable))[0]))

        for i in range(0, bhPointsFields.rowCount):
            relateFieldB = bhPointsFields.getValue(i, 0)
            depthDrillField = bhPointsFields.getValue(i, 1)
            depthBDRKField = bhPointsFields.getValue(i, 2)
            complDateField = bhPointsFields.getValue(i, 3)

        for i in range(0, lithTableFields.rowCount):
            relateFieldL = lithTableFields.getValue(i, 0)
            depthTopFieldL = lithTableFields.getValue(i, 1)
            depthBotFieldL = lithTableFields.getValue(i, 2)

        for i in range(0, scrnTableFields.rowCount):
            relateFieldS = scrnTableFields.getValue(i, 0)
            depthTopFieldS = scrnTableFields.getValue(i, 1)
            depthBotFieldS = scrnTableFields.getValue(i, 2)

        arcpy.management.CopyFeatures(in_features=bhPoints,
                                      out_feature_class=newBhPoints)
        arcpy.management.CopyRows(in_rows=lithTable,
                                  out_table=newLithTable)
        if scrnTable == "":
            pass
        else:
            arcpy.management.CopyRows(in_rows=scrnTable,
                                      out_table=newScrnTable)

        # Boreholes...
        arcpy.management.AlterField(in_table=newBhPoints,
                                    field=depthDrillField,
                                    new_field_name="BOREH_DEPTH")
        arcpy.management.AlterField(in_table=newBhPoints,
                                    field=relateFieldB,
                                    new_field_name="WELLID")
        if depthBDRKField == "":
            pass
        else:
            arcpy.management.AlterField(in_table=newBhPoints,
                                        field=depthBDRKField,
                                        new_field_name="DEPTH_2_BDRK")
        if complDateField == "":
            pass
        else:
            arcpy.management.AlterField(in_table=newBhPoints,
                                        field=complDateField,
                                        new_field_name="CONST_DATE")

        # Lithology table...
        arcpy.management.AlterField(in_table=newLithTable,
                                    field=relateFieldL,
                                    new_field_name="WELLID")
        arcpy.management.AlterField(in_table=newLithTable,
                                    field=depthTopFieldL,
                                    new_field_name="DEPTH_TOP")
        arcpy.management.AlterField(in_table=newLithTable,
                                    field=depthBotFieldL,
                                    new_field_name="DEPTH_BOT")

        if scrnTable == "":
            pass
        else:
            # Screens table...
            arcpy.management.AlterField(in_table=newScrnTable,
                                        field=relateFieldS,
                                        new_field_name="WELLID")
            arcpy.management.AlterField(in_table=newScrnTable,
                                        field=depthTopFieldS,
                                        new_field_name="DEPTH_TOP")
            arcpy.management.AlterField(in_table=newScrnTable,
                                        field=depthBotFieldS,
                                        new_field_name="DEPTH_BOT")
    else:
        newBhPoints = bhPoints
        newLithTable = lithTable
        newScrnTable = scrnTable
    AddMsgAndPrint("Boreholes: {}\nLithology: {}\nScreens: {}".format(os.path.basename(newBhPoints),
                                                                      os.path.basename(newLithTable),
                                                                      os.path.basename(newScrnTable)))
    for i in range(0, symbols.rowCount):
        wellSymbols = symbols.getValue(i, 0)
        scrnSymbols = symbols.getValue(i, 1)
except:
    AddMsgAndPrint("ERROR 001: Failed to format user datasets to acceptable dataset for borehole tool.",2)
    raise SystemError
for Value in allValue:
    try:
        FDSname = "XSEC_{}".format(Value)
        outFDS = os.path.join(outGDB,FDSname)
        if not arcpy.Exists(outFDS):
            AddMsgAndPrint("    Making final output dataset {} in {}".format(os.path.basename(outFDS),outGDB))
            arcpy.management.CreateFeatureDataset(outGDB,os.path.basename(outFDS),unknown)
    except:
        AddMsgAndPrint("ERROR 001: Failed to create the feature dataset for {}".format(Value))
        raise SystemError

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("BEGIN BOREHOLE CREATION")
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
            arcpy.ddd.InterpolateShape(dem, "lineLayers", z_line)
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
    except:
        AddMsgAndPrint("ERROR 002: Failed to create the elevation route polyline for {}".format(Value))
        raise SystemError
    try:
        #arcpy.SetProgressor("step","Creating borehole sticks for {}...".format(Value))
        AddMsgAndPrint("    Creating borehole sticks for {}...".format(Value))
        boreholeNear = arcpy.management.SelectLayerByLocation(
            in_layer=newBhPoints,
            overlap_type="WITHIN_A_DISTANCE",
            select_features=zm_line,
            search_distance=buff
        )
        zBoreholes = "XSEC_{}_zBoreholes".format(Value)
        arcpy.ddd.InterpolateShape(dem, boreholeNear, zBoreholes)
        try:
            arcpy.management.AddField(zBoreholes, "zDEM", "FLOAT")
        except:
            pass
        try:
            arcpy.management.CalculateField(zBoreholes, "zDEM", "!SHAPE.FIRSTPOINT.Z!", "PYTHON3")
        except:
            arcpy.management.CalculateField(zBoreholes, "zDEM", 0, "PYTHON3")
        zField = "zDEM"
        arcpy.management.SelectLayerByAttribute(bhPoints, "CLEAR_SELECTION")

        rProps = "rkey POINT M fmp"
        eventTable = locateEvents_Table(pts=zBoreholes, sel_dist=buff, event_props=rProps, z_type="Z")
        eventLayer = "XSEC_{}_Events"
        arcpy.lr.MakeRouteEventLayer(zm_line, checkField, eventTable, rProps, eventLayer, "#", "#", "ANGLE_FIELD",
                                     "TANGENT")
        locPoints = os.path.join(scratchDir, "XSEC_{}_Located".format(Value))
        arcpy.management.CopyFeatures(eventLayer, locPoints)
        arcpy.management.AddField(locPoints, "DistFromSection", "FLOAT")
        arcpy.management.AddField(locPoints, "LocalXSEC_Azimuth", "FLOAT")

        bhLines = boreholes(locatedPoints=locPoints)
    except:
        AddMsgAndPrint("ERROR 003: Failed to create the boreholes for {}".format(Value),2)
        raise SystemError
    try:
        AddMsgAndPrint("    Segmenting {} for lithology sticks...".format(Value))
        arcpy.SetProgressor("step", "Begin {}...".format(Value), 0, 15, 1)
        lithRoute = os.path.join(scratchDir, "XSEC_{}_bhRoutes_lith".format(Value))
        testAndDelete(lithRoute)
        arcpy.SetProgressorPosition()
        #arcpy.SetProgressorLabel("Repairing geometry...")
        #arcpy.management.RepairGeometry(
        #    in_features=bhLines,
        #    delete_null="DELETE_NULL",
        #    validation_method="ESRI"
        #)
        arcpy.SetProgressorPosition()
        arcpy.SetProgressorLabel("Create route...")
        #createRoute_Timer(bhLines,lithRoute)
        arcpy.lr.CreateRoutes(bhLines, "WELLID", lithRoute, "ONE_FIELD", "BOREH_DEPTH", "#", "UPPER_LEFT")
        arcpy.SetProgressorPosition()
        arcpy.SetProgressorLabel("Selecting lithology table of wells in area...")
        wellIds = []
        with arcpy.da.SearchCursor(bhLines, ["WELLID"]) as cursor:
            for row in cursor:
                wellIds.append(row[0])
            del row, cursor
        routeLiths = arcpy.management.SelectLayerByAttribute(
            in_layer_or_view=newLithTable,
            selection_type="ADD_TO_SELECTION",
            where_clause="WELLID IN {}".format(wellIds).replace("[","(").replace("]",")"),
            invert_where_clause=None)
        arcpy.SetProgressorPosition()
        #while int(arcpy.management.GetCount(lithRoute)[0]) == 0:
        #    arcpy.lr.CreateRoutes(bhLines, "relateid", lithRoute, "ONE_FIELD", "depth_drll", "#", "UPPER_LEFT")
        #else:
        #    pass
        #arcpy.SetProgressorPosition()
        arcpy.SetProgressorLabel("Make route event layer...")
        Lprop = "WELLID LINE depth_top depth_bot"
        arcpy.lr.MakeRouteEventLayer(
            in_routes=lithRoute,
            route_id_field="WELLID",
            in_table=routeLiths,
            in_event_properties=Lprop,
            out_layer="lyr2",
            add_error_field="ERROR_FIELD"
        )
        arcpy.SetProgressorPosition()
        arcpy.SetProgressorLabel("Exporting segments temporary layer to permanent feature class...")
        lithInterval = os.path.join(scratchDir, "XSEC_{}_intervalsLith".format(Value))
        testAndDelete(lithInterval)
        arcpy.SetProgressorPosition()
        #arcpy.conversion.ExportFeatures(
        #    in_features="lyr2",
        #    out_features=lithInterval,
        #)
        arcpy.conversion.ExportFeatures(
            in_features="lyr2",
            out_features=lithInterval
        )
        with arcpy.da.UpdateCursor(lithInterval,["LOC_ERROR"]) as cursor:
            for row in cursor:
                if row[0] == "ROUTE NOT FOUND":
                    cursor.deleteRow()
            del row, cursor
        arcpy.SetProgressorPosition()
        arcpy.SetProgressorLabel("Formatting fields...")
        arcpy.SetProgressorPosition()
        arcpy.management.AddField(lithInterval, "Dist2Xsec", "FLOAT")
        arcpy.SetProgressorPosition()
        arcpy.management.AddField(lithInterval, "PERCENT_DIST", "FLOAT")
        arcpy.env.qualifiedFieldNames = False
        arcpy.management.JoinField(lithInterval, "WELLID", locPoints, "WELLID", "Distance")
        arcpy.SetProgressorPosition()
        arcpy.management.CalculateField(lithInterval, "Dist2Xsec", "abs(!Distance!)", "PYTHON3")
        arcpy.SetProgressorPosition()
        arcpy.management.CalculateField(lithInterval, "PERCENT_DIST", "(!Dist2Xsec!/{}) * 100".format(buff.split(" ")[0]), "PYTHON3")
        arcpy.SetProgressorPosition()
        arcpy.management.DeleteField(lithInterval, "Distance")
        arcpy.SetProgressorPosition()
        finalLith = os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)), "XSEC_{}_LITH_{}x".format(Value, ve))
        testAndDelete(finalLith)
        arcpy.SetProgressorPosition()
        if stickForm == "Polygon":
            arcpy.SetProgressorLabel("Polygon selected. Creating buffer of sticks...")
            arcpy.analysis.Buffer(lithInterval, finalLith, "25 Unknown", "FULL", "FLAT", "NONE", None, "PLANAR")
            arcpy.management.DeleteField(finalLith, ["BUFF_DIST", "ORIG_FID"])
        else:
            arcpy.SetProgressorLabel("Copying sticks to final feature class...")
            arcpy.management.CopyFeatures(lithInterval, finalLith)
        if custom == "true":
            arcpy.management.AlterField(in_table=finalLith,
                                        field="WELLID",
                                        new_field_name=relateFieldL)
            arcpy.management.AlterField(in_table=finalLith,
                                        field="DEPTH_TOP",
                                        new_field_name=depthTopFieldL)
            arcpy.management.AlterField(in_table=finalLith,
                                        field="DEPTH_BOT",
                                        new_field_name=depthBotFieldL)
        else:
            pass
        arcpy.SetProgressorPosition()
        arcpy.ResetProgressor()
    except:
        AddMsgAndPrint("ERROR 004: Failed to create lithology sticks for {}".format(Value),2)
        raise SystemError
    try:
        if scrnTable == "":
            AddMsgAndPrint("No screens defined. Skipping step...")
            pass
        else:
            arcpy.SetProgressorLabel("Selecting screens table of wells in area...")
            routeScrns = arcpy.management.SelectLayerByAttribute(
                in_layer_or_view=newLithTable,
                selection_type="ADD_TO_SELECTION",
                where_clause="WELLID IN {}".format(wellIds).replace("[", "(").replace("]", ")"),
                invert_where_clause=None)
            arcpy.SetProgressorPosition()
            AddMsgAndPrint("    Segmenting {} for screen sticks...".format(Value))
            Lprop = "WELLID LINE depth_top depth_bot"
            arcpy.lr.MakeRouteEventLayer(
                in_routes=lithRoute,
                route_id_field="WELLID",
                in_table=routeScrns,
                in_event_properties=Lprop,
                out_layer="lyr3",
                add_error_field="ERROR_FIELD"
            )
            scrnsInterval = os.path.join(scratchDir, "XSEC_{}_intervalsScrns".format(Value))
            testAndDelete(scrnsInterval)
            #arcpy.conversion.ExportFeatures(
            #    in_features="lyr3",
            #    out_features=scrnsInterval
            #)
            arcpy.conversion.ExportFeatures(
                in_features="lyr3",
                out_features=scrnsInterval,
                where_clause="LOC_ERROR <> 'ROUTE NOT FOUND'"
            )
            arcpy.management.AddField(scrnsInterval, "Dist2Xsec", "FLOAT")
            arcpy.management.AddField(scrnsInterval, "PERCENT_DIST", "FLOAT")
            arcpy.env.qualifiedFieldNames = False
            arcpy.management.JoinField(scrnsInterval, "WELLID", locPoints, "WELLID", "Distance")
            arcpy.management.CalculateField(scrnsInterval, "Dist2Xsec", "abs(!Distance!)", "PYTHON3")
            arcpy.management.CalculateField(scrnsInterval, "PERCENT_DIST", "(!Dist2Xsec!/{}) * 100".format(buff.split(" ")[0]), "PYTHON3")
            arcpy.management.DeleteField(scrnsInterval,"Distance")
            finalScrns = os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)), "XSEC_{}_SCRNS_{}x".format(Value, ve))
            testAndDelete(finalScrns)
            if stickForm == "Polygon":
                arcpy.analysis.Buffer(scrnsInterval, finalScrns, "25 Unknown", "FULL", "FLAT", "NONE", None, "PLANAR")
                arcpy.management.DeleteField(finalScrns, ["BUFF_DIST", "ORIG_FID"])
            else:
                arcpy.management.CopyFeatures(scrnsInterval, finalScrns)
            if custom == "true":
                arcpy.management.AlterField(in_table=finalScrns,
                                            field="WELLID",
                                            new_field_name=relateFieldS)
                arcpy.management.AlterField(in_table=finalScrns,
                                            field="DEPTH_TOP",
                                            new_field_name=depthTopFieldS)
                arcpy.management.AlterField(in_table=finalScrns,
                                            field="DEPTH_BOT",
                                            new_field_name=depthBotFieldS)
            else:
                pass
    except:
        AddMsgAndPrint("ERROR 005: Failed to create screen sticks for {}".format(Value), 2)
        raise SystemError
    try:
        AddMsgAndPrint("    Cleaning {}...".format(os.path.basename(scratchDir)))
        xsecMap = prj.listMaps('XSEC_{}'.format(Value))[0]

        if scrnTable == "":
            arcpy.management.Delete([zm_line, lithInterval, z_line, locPoints, eventTable, zBoreholes, bhLines,lithRoute])
        else:
            arcpy.management.Delete([zm_line, lithInterval, z_line, locPoints, eventTable, scrnsInterval, zBoreholes, bhLines,lithRoute])
            arcpy.management.SelectLayerByAttribute(newScrnTable, "CLEAR_SELECTION")
        arcpy.management.DeleteField(lineLayer, checkField)
        arcpy.management.SelectLayerByAttribute(newLithTable, "CLEAR_SELECTION")
        xsecMap.addDataFromPath(finalLith)
        if scrnTable == "":
            pass
        else:
            xsecMap.addDataFromPath(finalScrns)
        # *Importing a custom layer file was not applying to final dataset. Omit for now.*
        #try:
        #    if wellSymbols == "":
        #        xsecMap.addDataFromPath(finalLith)
        #    else:
        #        xsecMap.addDataFromPath(wellSymbols)
        #        wellSymbolsLyr = xsecMap.listLayers()[0]
        #        wellSymbolsLyr.visible = False
        #        wellSymbolsLyr.name = wellSymbolsLyr.name.replace(str(wellSymbolsLyr.name), "WellSticksSymbols")
        #        xsecMap.addDataFromPath(finalLith)
        #        finalLithLyr = xsecMap.listLayers(os.path.basename(finalLith))[0]

        #        arcpy.management.ApplySymbologyFromLayer(
        #            in_layer=finalLithLyr,
        #            in_symbology_layer=wellSymbolsLyr,
        #            update_symbology="UPDATE"
        #        )
        #    if scrnSymbols == "":
        #        if scrnTable == "":
        #            xsecMap.addDataFromPath(finalScrns)
        #        else:
        #            pass
        #    else:
        #        lf = arcpy.mp.LayerFile(scrnSymbols)
        #        xsecMap.addLayer(lf,"BOTTOM")
        #        scrnSymbolLyr = xsecMap.listLayers()[2]
        #        scrnSymbolLyr.visible = False
        #        scrnSymbolLyr.name = scrnSymbolLyr.name.replace(str(scrnSymbolLyr.name), "ScreenSticksSymbols")
        #        xsecMap.addDataFromPath(finalScrns)
        #        finalScrnsLyr = xsecMap.listLayers(os.path.basename(finalScrns))[0]
        #        arcpy.management.ApplySymbologyFromLayer(
        #            in_layer=finalScrnsLyr,
        #            in_symbology_layer=scrnSymbolLyr,
        #            update_symbology="DEFAULT"
        #        )
        #    prj.save()
        #except:
        #    AddMsgAndPrint("Cannot support Unique Symbology",1)
        #    pass
    except:
        AddMsgAndPrint("ERROR 006: Failed to clean up {}".format(os.path.basename(scratchDir)),2)
        raise SystemError

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("BEGIN DEM TOPOGRAPHIC SURFACE CREATION")
featExtent = os.path.join(scratchDir, "ProjectAreaExtent_TOPO")
testAndDelete(featExtent)
arcpy.ddd.RasterDomain(dem, featExtent, "POLYGON")
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
            arcpy.ddd.InterpolateShape(dem, "lineLayers", z_line)
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

        profileName = "XSEC_{}_TOPO_{}x".format(Value, ve)
        profilePath = os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)), profileName)
        testAndDelete(profilePath)
        arcpy.management.CreateFeatureclass(os.path.join(outGDB,"XSEC_{}".format(Value)), profileName, "POLYLINE",
                                            zm_line, spatial_reference=unknown)
        arcpy.management.AddField(profilePath, "{}_ID".format(profileName), "TEXT", field_length=50, field_is_nullable="NON_NULLABLE")

        # Providing the list of fields that come from "zm_line"
        fldOBJ = arcpy.ListFields(zm_line)
        flds = [f.name for f in fldOBJ if f.type != "Geometry"]
        flds.append("SHAPE@")

        # Providing search cursor on "zm_line" with the fields listed from "fldOBJ"
        inRows = arcpy.da.SearchCursor(zm_line, flds)
        # Extending the list of fields to include the new ID field in the output
        # This is now at the end of the list, with an index of -1
        flds.append("{}_ID".format(profileName))
        outRows = arcpy.da.InsertCursor(profilePath, flds)
        oidName = [f.name for f in fldOBJ if f.type == "OID"][0]
        oidIndex = outRows.fields.index(oidName)

        i = 0
        for row in inRows:
            if elevUnits == "Meters":
                i = i + 1
                vals = list(row).copy()
                # Extend vals by one more element to make room for the ID value
                vals.append("")
                array = []
                line = row[-1]
                for pnt in line[0]:
                    X = pnt.M
                    Y = pnt.Z
                    array.append((X,Y * float(ve)))
                vals[-2] = array
                vals[-1] = "{}SP{}".format(Value,i)
                outRows.insertRow(vals)
            if elevUnits == "Feet":
                i = i + 1
                vals = list(row).copy()
                # Extend vals by one more element to make room for the ID value
                vals.append("")
                array = []
                line = row[-1]
                for pnt in line[0]:
                    X = pnt.M
                    Y = pnt.Z * 0.3048
                    array.append((X, Y * float(ve)))
                vals[-2] = array
                vals[-1] = "{}SP{}".format(Value, i)
                outRows.insertRow(vals)
    except:
        AddMsgAndPrint("ERROR 007: Failed to create the topographic surface for {}".format(Value), 2)
        raise SystemError
    try:
        AddMsgAndPrint("    Cleaning {} and symbolizing...".format(os.path.basename(scratchDir)))
        xsecMap = prj.listMaps('XSEC_{}'.format(Value))[0]
        xsecMap.addDataFromPath(profilePath)
        del inRows, outRows
        arcpy.management.Delete([zm_line,z_line])
        arcpy.management.DeleteField(lineLayer, checkField)
        profileLayer = xsecMap.listLayers(os.path.splitext(os.path.basename(profilePath))[0])[0]

        symProfile = profileLayer.symbology

        # Profile symbology...
        symProfile.renderer.symbol.outlineColor = {'RGB': [56, 168, 0, 100]}
        symProfile.renderer.symbol.outlineWidth = 2
        profileLayer.symbology = symProfile
        prj.save()
    except:
        AddMsgAndPrint("ERROR 008: Failed to clean up {}".format(os.path.basename(scratchDir)),2)
        raise SystemError

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
                eraseFeat = os.path.join(scratchDir, "BDRK_ERASE")
                testAndDelete(eraseFeat)
                arcpy.analysis.Erase(
                    in_features="lineLayers",
                    erase_features=featExtent,
                    out_feature_class=eraseFeat,
                    cluster_tolerance=None
                )
                singleFeat = os.path.join(scratchDir, "BDRK_ERASE_SINGLE")
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
            AddMsgAndPrint("ERROR 009: Failed to create bedrock surface for {}".format(Value), 2)
            raise SystemError
        try:
            AddMsgAndPrint("    Creating the confidence zone polygon feature class...")
            bdrkpoints = arcpy.management.SelectLayerByAttribute(
                in_layer_or_view=newBhPoints,
                selection_type="NEW_SELECTION",
                where_clause="DEPTH_2_BDRK > 0",
                invert_where_clause=None)
            bdrkBuff = os.path.join(scratchDir,"XSEC_{}_BUFF_BDRK_{}{}".format(Value,buff.split(" ")[0],buff.split(" ")[1]))

            arcpy.analysis.Buffer(bdrkpoints,bdrkBuff,buff,"FULL","ROUND","ALL",None,"PLANAR")
            unionBDRK = os.path.join(scratchDir, "XSEC_{}_UNION_BDRK".format(Value))
            inFeatures = [featExtent, bdrkBuff]
            arcpy.analysis.Union(inFeatures, unionBDRK, "ONLY_FID", None, "GAPS")
            bdrkConfidence = os.path.join(os.path.dirname(newBhPoints), "XSEC_{}_BDRK_ConZone".format(Value))
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
            placeEvents(inRoutes=zm_line,
                        idRteFld=checkField,
                        eventTable=conEventsTable,
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
            arcpy.management.Delete([zm_line,z_line,bdrkBuff,unionBDRK,bdrkConfidence,eraseFeat,singleFeat,conEventsTable,locatedEvents_bdrk,featExtent])
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

            featExtent = os.path.join(scratchDir,
                                      "ProjectAreaExtent_{}".format(os.path.splitext(os.path.basename(raster))[0]))
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
                    buffWW = os.path.basename(newBhPoints) + "_{}{}_buff_AllYears".format(buff.split(" ")[0],buff.split(" ")[1])
                    arcpy.analysis.Buffer(newBhPoints, buffWW, "{}".format(buff), "FULL", "ROUND", "ALL", None, "PLANAR")
                    unionWW = os.path.basename(newBhPoints) + "_Union"
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
                        in_layer_or_view=newBhPoints,
                        selection_type="NEW_SELECTION",
                        where_clause="CONST_DATE >= timestamp '{}-01-01 00:00:00' And CONST_DATE <= timestamp '{}-12-31 00:00:00'".format(startYear,endYear),
                        invert_where_clause=None)
                    buffWW = os.path.basename(newBhPoints) + "_{}{}_buff_{}_{}".format(buff.split(" ")[0],
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
                arcpy.management.SelectLayerByAttribute(newBhPoints, "CLEAR_SELECTION")
                arcpy.management.Delete([zm_line,z_line,buffWW,unionWW,confidenceZone,singleFeat,eraseFeat,locatedEvents_gwl,conEventsTable])
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

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("BEGIN CREATING GRID LINES FOR CROSS-SECTIONS")
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
            arcpy.ddd.InterpolateShape(dem, "lineLayers", z_line)
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

        AddMsgAndPrint("    Creating cross-section frame for {}".format(Value))
        descGridTB = arcpy.Describe(os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)), "XSEC_{}_LITH_{}x".format(Value, ve)))
        descGridRight = arcpy.Describe(os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)), "XSEC_{}_TOPO_{}x".format(Value, ve)))
        if arcpy.Exists(os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)), "XSEC_{}_BDRK_{}x".format(Value, ve))):
            descGridBot = arcpy.Describe(os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)), "XSEC_{}_BDRK_{}x".format(Value, ve)))
        Xmin = 0
        Xmax = descGridRight.extent.XMax
        bhYmax = descGridTB.extent.YMax
        if arcpy.Exists(os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)), "XSEC_{}_BDRK_{}x".format(Value, ve))):
            bdrkYmin = descGridBot.extent.ZMin
            bhYmin = descGridTB.extent.YMin
            if elevUnits == "Feet":
                if bhYmin > ((bdrkYmin * 0.3048)*int(ve)):
                    Ymin = ((bdrkYmin * 0.3048)*int(ve))
                elif bhYmin < ((bdrkYmin * 0.3048)*int(ve)):
                    Ymin = bhYmin
                elif bhYmin == ((bdrkYmin * 0.3048)*int(ve)):
                    # Doesn't matter which one since they have the same elevation minimum. This will likely never happen, but just in case it does...
                    Ymin = bhYmin
            if elevUnits == "Meters":
                if bhYmin > (bdrkYmin * int(ve)):
                    Ymin = (bdrkYmin * int(ve))
                elif bhYmin < (bdrkYmin *int(ve)):
                    Ymin = bhYmin
                elif bhYmin == (bdrkYmin * int(ve)):
                    # Doesn't matter which one since they have the same elevation minimum. This will likely never happen, but just in case it does...
                    Ymin = bhYmin
        else:
            bhYmin = descGridTB.extent.YMin
            Ymin = bhYmin
        # arcpy.AddMessage("Minimum X: {0}\nMaximum X: {1}\nMaximum Borehole Y: {2}\nMinimum Borehole Y: {3}\nMaximum Topo Y: {4}\nMinimum Topo Y: {5}".format(Xmin,Xmax,bhYmax,bhYmin,descGridRight.extent.YMax,descGridRight.extent.YMin))
        if descGridRight.extent.YMax > bhYmax:
            Ymax = descGridRight.extent.YMax
        elif descGridRight.extent.YMax < bhYmax:
            Ymax = bhYmax
        elif descGridRight.extent.YMax == bhYmax:
            # Doesn't matter which one since they have the same elevation maximum. This will likely never happen, but just in case it does...
            Ymax = bhYmax

        frameName = "XSEC_{}_{}x_Frame_{}".format(Value,ve,elevUnits)
        framePath = os.path.join(os.path.join(outGDB,"XSEC_{}".format(Value)),frameName)
        testAndDelete(framePath)
        arcpy.management.CreateFeatureclass(os.path.join(outGDB,"XSEC_{}".format(Value)),frameName,"POLYLINE",
                                            spatial_reference=unknown)
        arcpy.management.AddField(framePath, "TYPE", "TEXT", field_length=100)
        arcpy.management.AddField(framePath, "LABEL", "TEXT", field_length=100)
        arcpy.management.AddField(framePath, "{}_ID".format(frameName), "TEXT", field_length=50)
        idPref = "{}FM".format(Value)
        inRows = arcpy.da.SearchCursor(zm_line, "SHAPE@")
        outRows = arcpy.da.InsertCursor(framePath,["TYPE","LABEL","SHAPE@","{}_ID".format(frameName)])

        labelName = "XSEC_{}_{}x_Labels_{}".format(Value, ve,elevUnits)
        labelPath = os.path.join(os.path.join(outGDB, "XSEC_{}".format(Value)), labelName)
        testAndDelete(labelPath)
        arcpy.management.CreateFeatureclass(os.path.join(outGDB, "XSEC_{}".format(Value)), labelName, "POINT",
                                            spatial_reference=unknown)
        arcpy.management.AddField(labelPath, "TYPE", "TEXT", field_length=100)
        arcpy.management.AddField(labelPath, "LABEL", "TEXT", field_length=100)
        arcpy.management.AddField(labelPath, "{}_ID".format(labelName), "TEXT", field_length=50)
        labelRows = arcpy.da.InsertCursor(labelPath, ["TYPE", "LABEL", "SHAPE@", "{}_ID".format(labelName)])

        for i in range(0, grids.rowCount):
            xInt = grids.getValue(i, 0)
            xUnits = grids.getValue(i, 1)
            yInt = grids.getValue(i, 2)
            yUnits = grids.getValue(i, 3)

            AddMsgAndPrint("Distance Units: {} {}".format(xInt,xUnits))
            AddMsgAndPrint("Elevation Units: {} {}".format(yInt, yUnits))
            if yUnits == "Meters":
                botY = round2int(x=(Ymin / float(ve)),
                                 base=float(yInt))
                if int(Ymin/float(ve)) < botY:
                    newYmin = (botY*float(ve)) - (int(yInt)*float(ve))
                else:
                    newYmin = botY*float(ve)
            else:
                botY = round2int(x=((Ymin / float(ve))/0.3048),
                                 base=float(yInt))
                if int((Ymin/float(ve))/0.3048) < botY:
                    newYmin = (botY*float(ve)*0.3048) - (int(yInt)*float(ve)*0.3048)
                else:
                    newYmin = botY * 0.3048*float(ve)

            # Define the minimum and maximum elevation and distance tick marks...
            if yUnits == "Meters":
                elevTickMin = round2int(x=newYmin // float(ve),
                                        base=float(yInt))
                elevTickMax = round2int(x=Ymax // float(ve),
                                        base=float(yInt))
            elif yUnits == "Feet":
                elevTickMin = round2int(x=(newYmin // float(ve))/0.3048,
                                        base=float(yInt))
                elevTickMax = round2int(x=(Ymax // float(ve))/0.3048,
                                        base=float(yInt))

            if xUnits == "Meters":
                distTickMin = round2int(x=Xmin,
                                        base=float(xInt))
                distTickMax = round2int(x=Xmax,
                                        base=float(xInt))
                if distTickMax > Xmax:
                    newDistTickMax = distTickMax - (float(xInt))
                elif distTickMax < Xmax:
                    newDistTickMax = distTickMax
                elif distTickMax == Xmax:
                    newDistTickMax = distTickMax
                distList = np.arange(distTickMin, newDistTickMax+1, float(xInt))
            elif xUnits == "Kilometers":
                distTickMin = round2int(x=Xmin/1000,
                                        base=float(xInt))
                distTickMax = round2int(x=Xmax/1000,
                                        base=float(xInt))
                if distTickMax > (Xmax / 1000):
                    newDistTickMax = distTickMax - (float(xInt))
                elif distTickMax < (Xmax / 1000):
                    newDistTickMax = distTickMax
                elif distTickMax == (Xmax / 1000):
                    newDistTickMax = distTickMax
                distList = np.arange(distTickMin, newDistTickMax+1, float(xInt))
            elif xUnits == "Feet":
                distTickMin = round2int(x=Xmin//0.3048,
                                        base=float(xInt))
                distTickMax = round2int(x=Xmax//0.3048,
                                        base=float(xInt))
                if distTickMax > (Xmax / 0.3048):
                    newDistTickMax = distTickMax - (float(xInt))
                elif distTickMax < (Xmax / 0.3048):
                    newDistTickMax = distTickMax
                elif distTickMax == (Xmax / 0.3048):
                    newDistTickMax = distTickMax
                distList = np.arange(distTickMin, newDistTickMax+1, float(xInt))
            elif xUnits == "Miles":
                distTickMin = round2int(x=(Xmin//0.3048)/5280,
                                        base=float(xInt))
                distTickMax = round2int(x=(Xmax//0.3048)/5280,
                                        base=float(xInt))
                if distTickMax > ((Xmax / 0.3048)/5280):
                    newDistTickMax = distTickMax - (float(xInt))
                elif distTickMax < ((Xmax / 0.3048)/5280):
                    newDistTickMax = distTickMax
                elif distTickMax == ((Xmax / 0.3048)/5280):
                    newDistTickMax = distTickMax
                distList = np.arange(distTickMin, newDistTickMax+1, float(xInt))

            # Build out the frame for the cross-section...
            if yUnits == "Feet":
                if (elevTickMax * 0.3048 * float(ve)) < Ymax:
                    newElevTickMax = elevTickMax + int(yInt)
                    newYmax = (elevTickMax * 0.3048 * float(ve)) + (float(yInt) * 0.3048 * float(ve))
                elif (elevTickMax * 0.3048 * float(ve)) > Ymax:
                    newElevTickMax = elevTickMax
                    newYmax = (elevTickMax * 0.3048 * float(ve))
                elevList = np.arange(elevTickMin, newElevTickMax+1, float(yInt))
            elif yUnits == "Meters":
                if (elevTickMax * float(ve)) < Ymax:
                    newElevTickMax = elevTickMax + int(yInt)
                    newYmax = (elevTickMax * float(ve)) + (float(yInt) * float(ve))
                elif (elevTickMax * float(ve)) > Ymax:
                    newElevTickMax = elevTickMax
                    newYmax = (elevTickMax * float(ve))
                elevList = np.arange(elevTickMin, newElevTickMax+1, float(yInt))

            # Build the elevation tick intervals...
            c = 1
            for y in elevList:
                if yUnits == "Feet":
                    yVE = y * 0.3048 * float(ve)
                elif yUnits == "Meters":
                    yVE = y * float(ve)
                leftpnt = (Xmin,yVE)
                rightpnt = (Xmax, yVE)
                c = c + 1
                outRows.insertRow(["ELEVATION MARK",str(y),[leftpnt,rightpnt],"{}{}".format(idPref,c)])

            # Build the distance tick intervals...
            for x in distList:
                if xUnits == "Meters":
                    distpnt1 = (x, newYmin)
                    distpnt2 = (x, newYmax)
                elif xUnits == "Kilometers":
                    distpnt1 = (x * 1000, newYmin)
                    distpnt2 = (x * 1000, newYmax)
                elif xUnits == "Feet":
                    distpnt1 = (x * 0.3048, newYmin)
                    distpnt2 = (x * 0.3048, newYmax)
                elif xUnits == "Miles":
                    distpnt1 = ((x * 5280) * 0.3048, newYmin)
                    distpnt2 = ((x * 5280) * 0.3048, newYmax)
                c = c + 1
                outRows.insertRow(["DISTANCE MARK",str(x),[distpnt1,distpnt2],"{}{}".format(idPref, c)])
            array = []
            array.append((Xmin, newYmax))
            array.append((Xmin, newYmin))
            array.append((Xmax, newYmin))
            array.append((Xmax, newYmax))
            array.append((Xmin, newYmax))
            outRows.insertRow(["FRAME", "", array, "{}_1".format(idPref)])

            del outRows

            # Build the elevation points intervals...
            for y in elevList:
                if yUnits == "Feet":
                    yVE = y * 0.3048 * float(ve)
                elif yUnits == "Meters":
                    yVE = y * float(ve)
                elevPnt = [Xmin, yVE]
                c = c + 1
                labelRows.insertRow(["ELEVATION MARK", str(int(y)), elevPnt, "{}{}".format(idPref, c)])
            c = c + 1

            # Build the distance points intervals...
            for x in distList:
                if xUnits == "Meters":
                    distPnt = [x, newYmin]
                elif xUnits == "Kilometers":
                    distPnt = [x * 1000, newYmin]
                elif xUnits == "Feet":
                    distPnt = [x * 0.3048, newYmin]
                elif xUnits == "Miles":
                    distPnt = [(x * 5280) * 0.3048, newYmin]
                c = c + 1
                labelRows.insertRow(["DISTANCE MARK",str(int(x)),distPnt,"{}{}".format(idPref, c)])
    except:
        AddMsgAndPrint("ERROR 017: Could not create grid lines and labels for {}".format(Value),2)
        raise SystemError
    try:
        AddMsgAndPrint("Cleaning {} and visualizing new datasets...".format(os.path.basename(scratchDir)))
        xsecMap = prj.listMaps('XSEC_{}'.format(Value))[0]
        xsecMap.addDataFromPath(framePath)
        xsecMap.addDataFromPath(labelPath)
        gridLayer = xsecMap.listLayers(os.path.splitext(os.path.basename(framePath))[0])[0]
        labelLayer = xsecMap.listLayers(os.path.splitext(os.path.basename(labelPath))[0])[0]

        symLabels = labelLayer.symbology
        symGrids = gridLayer.symbology

        # Labels symbology...
        symLabels.renderer.symbol.color = {'RGB': [0, 0, 0, 0]}
        symLabels.renderer.symbol.outlineColor = {'RGB': [0, 0, 0, 0]}
        symLabels.renderer.symbol.outlineWidth = 2
        labelLayer.symbology = symLabels
        prj.save()

        # Grids symbology...
        symGrids.updateRenderer("UniqueValueRenderer")
        gridLayer.symbology = symGrids

        symGrids.renderer.fields = ["TYPE"]
        symGrids.renderer.removeValues({"TYPE": ["FRAME","DISTANCE MARK","ELEVATION MARK"]})
        gridLayer.symbology = symGrids
        symGrids.renderer.addValues({"Type": ["FRAME","DISTANCE MARK","ELEVATION MARK"]})
        gridLayer.symbology = symGrids
        for group in symGrids.renderer.groups:
            for item in group.items:
                if item.values[0][0] == "FRAME":
                    item.symbol.outlineColor = {'RGB': [0, 0, 0, 100]}
                    item.symbol.outlineWidth = 2
                    item.label = "Border Frame"
                    gridLayer.symbology = symGrids
                elif item.values[0][0] == "DISTANCE MARK":
                    item.symbol.outlineColor = {'RGB': [178, 178, 178, 100]}
                    item.symbol.outlineWidth = 0.5
                    item.label = "Grid Lines"
                    gridLayer.symbology = symGrids
                elif item.values[0][0] == "ELEVATION MARK":
                    item.symbol.outlineColor = {'RGB': [178, 178, 178, 100]}
                    item.symbol.outlineWidth = 0.5
                    item.label = "Grid Lines"
                    gridLayer.symbology = symGrids
        prj.save()

        try:
            cimObject = labelLayer.getDefinition("V3")
            lblClasses = cimObject.labelClasses
            #elevLblClass = arcpy.cim.CreateCIMObjectFromClassName("CIMLabelClass","V3")
            #elevLblClass.name = "Elevation"
            #elevLblClass.visibility = True
            #cimObject.labelClasses.append(elevLblClass)
            #labelLayer.setDefinition(cimObject)

            for lblClass in lblClasses:
                if lblClass.name == "Class 1":
                    lblClass.name = "Distance"
                    nlc_index = cimObject.labelClasses.index(lblClass)
                    newClass = cimObject.labelClasses.copy()[nlc_index]
                    cimObject.labelClasses.append(newClass)
                    labelLayer.setDefinition(cimObject)
                    break

            cimObject = labelLayer.getDefinition("V3")
            lblClasses = cimObject.labelClasses
            for lblClass in lblClasses:
                if lblClass.name == "Distance":
                    nlc_index = cimObject.labelClasses.index(lblClass)
                    if nlc_index != 0:
                        lblClass.name = "Elevation"
                        labelLayer.setDefinition(cimObject)

            # Place the labels correctly...
            lblClassDist_2 = cimObject.labelClasses[0]
            lblClassDist_2.maplexLabelPlacementProperties.pointPlacementMethod = "SouthOfPoint"
            lblClassDist_2.maplexLabelPlacementProperties.rotationProperties.enable = True
            lblClassDist_2.maplexLabelPlacementProperties.rotationProperties.additionalAngle = -45
            lblClassDist_2.maplexLabelPlacementProperties.primaryOffset = 10.0
            labelLayer.setDefinition(cimObject)

            lblClassElev_2 = cimObject.labelClasses[1]
            lblClassElev_2.maplexLabelPlacementProperties.pointPlacementMethod = "WestOfPoint"
            lblClassElev_2.maplexLabelPlacementProperties.primaryOffset = 10.0
            labelLayer.setDefinition(cimObject)

            labelLayer.showLabels = True

            if labelLayer.supports("SHOWLABELS"):
                lblClassDist = labelLayer.listLabelClasses()[0]
                lblClassDist.expressionEngine = "Arcade"
                lblClassDist.expression = '"<FNT name = {}>" + $feature.LABEL + "</FNT>"'.format("'Times New Roman'")
                lblClassDist.SQLQuery = "TYPE = 'DISTANCE MARK'"

                lblClassElev = labelLayer.listLabelClasses()[1]
                lblClassElev.expressionEngine = "Arcade"
                lblClassElev.expression = '"<FNT name = {}>" + $feature.LABEL + "</FNT>"'.format("'Times New Roman'")
                lblClassElev.SQLQuery = "TYPE = 'ELEVATION MARK'"
                lblClassElev.visible = True
            else:
                pass
            prj.save()



        except Exception as e:
            AddMsgAndPrint("Could not complete labels and symbology. Error Message: {}. Passing to final steps...".format(e),1)
            pass

        extentLyr = xsecMap.listLayers(os.path.splitext(os.path.basename(labelPath))[0])[0]
        xsecMap.defaultCamera.setExtent(arcpy.Describe(extentLyr).extent)
        xsecMap.openView()
        prj.save()
        del inRows, labelRows
        arcpy.management.Delete([zm_line,z_line])
        if custom == "true":
            arcpy.management.Delete([newBhPoints,newLithTable,newScrnTable])
        else:
            pass
    except:
        AddMsgAndPrint("ERROR 018: Failed to clean up {}".format(os.path.basename(scratchDir)),2)
        raise SystemError