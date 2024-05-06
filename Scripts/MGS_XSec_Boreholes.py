"""
MGS_XSec_Boreholes.py
Description: ArcToolbox tool script to create a set of cross-sections defined by the end user.
             Specifically built for ArcGIS Pro software.
Requirements: python, ArcGIS Pro
Author: Matthew Bell, Michigan Geological Survey, matthew.e.bell@wmich.edu
Date: 8/8/2023

Last updated: 8/8/2023
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
    eventLocTable = os.path.join(scratchDir, Value + "_bhEvents")
    testAndDelete(eventLocTable)
    arcpy.lr.LocateFeaturesAlongRoutes(pts,zm_line,checkField,sel_dist,eventLocTable,event_props)
    nRows = int(arcpy.GetCount_management(eventLocTable)[0])
    nPts = int(arcpy.GetCount_management(pts)[0])
    if nRows > nPts and not is_lines:
        arcpy.management.DeleteIdentical(eventLocTable, dupDetectField)
    arcpy.management.DeleteField(eventLocTable, dupDetectField)
    return eventLocTable

def boreholes(locatedPoints):
    bhLinesName = Value + "_bhLines"
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

# Determine if the data is a custom dataset or from the MGS Data Reformatting Script
custom = arcpy.GetParameterAsText(4)

# Borehole Points
bhPoints = arcpy.GetParameterAsText(5)

# Borehole Points Fields
bhPointsFields = arcpy.ValueTable(4)
bhPointsFields.loadFromString(arcpy.GetParameterAsText(6))

# Lithology Table
lithTable = arcpy.GetParameterAsText(7)

# Lithology Table Fields
lithTableFields = arcpy.ValueTable(3)
lithTableFields.loadFromString(arcpy.GetParameterAsText(8))

# Screens Table
scrnTable = arcpy.GetParameterAsText(9)

# Screens Table Fields
scrnTableFields = arcpy.ValueTable(3)
scrnTableFields.loadFromString(arcpy.GetParameterAsText(10))

# Vertical Exaggeration
ve = arcpy.GetParameterAsText(11)

# Selection Distance
buff = arcpy.GetParameterAsText(12)

# Polygon or Polyline?
stickForm = arcpy.GetParameterAsText(13)

# Symbologies for the different layers
symbols = arcpy.ValueTable(3)
symbols.loadFromString(arcpy.GetParameterAsText(14))

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
# Now, we need to implement any custom datasets into the mixture...
try:
    if custom == "true":
        newBhPoints = os.path.join(scratchDir,"{}_BH_MGS".format(os.path.splitext(os.path.basename(bhPoints))[0]))
        newLithTable = os.path.join(scratchDir,"{}_LITH_MGS".format(os.path.splitext(os.path.basename(lithTable))[0]))
        newScrnTable = os.path.join(scratchDir,"{}_SCRN_MGS".format(os.path.splitext(os.path.basename(scrnTable))[0]))
        for i in range(0,bhPointsFields.rowCount):
            relateFieldB = bhPointsFields.getValue(i,0)
            depthDrillField = bhPointsFields.getValue(i,1)
            depthBDRKField = bhPointsFields.getValue(i,2)
            complDateField = bhPointsFields.getValue(i,3)

        for i in range(0,lithTableFields.rowCount):
            relateFieldL = lithTableFields.getValue(i,0)
            depthTopFieldL = lithTableFields.getValue(i,1)
            depthBotFieldL = lithTableFields.getValue(i,2)

        for i in range(0,scrnTableFields.rowCount):
            relateFieldS = scrnTableFields.getValue(i,0)
            depthTopFieldS = scrnTableFields.getValue(i,1)
            depthBotFieldS = scrnTableFields.getValue(i,2)

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
        surfaceSymbols = symbols.getValue(i, 2)
except:
    AddMsgAndPrint("ERROR 001: Failed to format user datasets to acceptable dataset for borehole tool.",2)
    raise SystemError
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
        arcpy.management.SelectLayerByLocation(in_layer=newBhPoints,
                                               overlap_type="WITHIN_A_DISTANCE",
                                               select_features=zm_line,
                                               search_distance=buff)
        zBoreholes = "XSEC_{}_zBoreholes".format(Value)
        arcpy.ddd.InterpolateShape(dem, newBhPoints, zBoreholes)
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
        if lithTable == "":
            AddMsgAndPrint("No lithology defined. Skipping step...")
            pass
        else:
            AddMsgAndPrint("    Segmenting {} for lithology sticks...".format(Value))
            arcpy.SetProgressor("step", "Begin {}...".format(Value), 0, 15, 1)
            lithRoute = os.path.join(scratchDir, "XSEC_{}_bhRoutes_lith".format(Value))
            testAndDelete(lithRoute)
            arcpy.SetProgressorPosition()
            # arcpy.SetProgressorLabel("Repairing geometry...")
            # arcpy.management.RepairGeometry(
            #    in_features=bhLines,
            #    delete_null="DELETE_NULL",
            #    validation_method="ESRI"
            # )
            arcpy.SetProgressorPosition()
            arcpy.SetProgressorLabel("Create route...")
            # createRoute_Timer(bhLines,lithRoute)
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
                where_clause="WELLID IN {}".format(wellIds).replace("[", "(").replace("]", ")"),
                invert_where_clause=None)
            arcpy.SetProgressorPosition()
            # while int(arcpy.management.GetCount(lithRoute)[0]) == 0:
            #    arcpy.lr.CreateRoutes(bhLines, "relateid", lithRoute, "ONE_FIELD", "depth_drll", "#", "UPPER_LEFT")
            # else:
            #    pass
            # arcpy.SetProgressorPosition()
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
            # arcpy.conversion.ExportFeatures(
            #    in_features="lyr2",
            #    out_features=lithInterval,
            # )
            arcpy.conversion.ExportFeatures(
                in_features="lyr2",
                out_features=lithInterval
            )
            with arcpy.da.UpdateCursor(lithInterval, ["LOC_ERROR"]) as cursor:
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
            arcpy.management.CalculateField(lithInterval, "PERCENT_DIST",
                                            "(!Dist2Xsec!/{}) * 100".format(buff.split(" ")[0]), "PYTHON3")
            arcpy.SetProgressorPosition()
            arcpy.management.DeleteField(lithInterval, "Distance")
            arcpy.SetProgressorPosition()
            finalLith = os.path.join(os.path.join(outGDB, "XSEC_{}".format(Value)),
                                     "XSEC_{}_LITH_{}x".format(Value, ve))
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
        AddMsgAndPrint("ERROR 004: Failed to create lithology sticks for {}".format(Value), 2)
        raise SystemError
    try:
        if scrnTable == "":
            AddMsgAndPrint("No screens defined. Skipping step...")
            pass
        else:
            if lithTable == "":
                lithRoute = os.path.join(scratchDir, "XSEC_{}_bhRoutes_lith".format(Value))
                testAndDelete(lithRoute)
                arcpy.SetProgressorPosition()
                # arcpy.SetProgressorLabel("Repairing geometry...")
                # arcpy.management.RepairGeometry(
                #    in_features=bhLines,
                #    delete_null="DELETE_NULL",
                #    validation_method="ESRI"
                # )
                arcpy.SetProgressorPosition()
                arcpy.SetProgressorLabel("Create route...")
                # createRoute_Timer(bhLines,lithRoute)
                arcpy.lr.CreateRoutes(bhLines, "WELLID", lithRoute, "ONE_FIELD", "BOREH_DEPTH", "#", "UPPER_LEFT")
            else:
                pass
            arcpy.SetProgressorLabel("Selecting screens table of wells in area...")
            arcpy.SetProgressorPosition()
            AddMsgAndPrint("    Segmenting {} for screen sticks...".format(Value))
            Lprop = "WELLID LINE depth_top depth_bot"
            arcpy.lr.MakeRouteEventLayer(
                in_routes=lithRoute,
                route_id_field="WELLID",
                in_table=scrnTable,
                in_event_properties=Lprop,
                out_layer="lyr3",
                add_error_field="ERROR_FIELD"
            )
            scrnsInterval = os.path.join(scratchDir, "XSEC_{}_intervalsScrns".format(Value))
            testAndDelete(scrnsInterval)
            # arcpy.conversion.ExportFeatures(
            #    in_features="lyr3",
            #    out_features=scrnsInterval
            # )
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
            arcpy.management.CalculateField(scrnsInterval, "PERCENT_DIST",
                                            "(!Dist2Xsec!/{}) * 100".format(buff.split(" ")[0]), "PYTHON3")
            arcpy.management.DeleteField(scrnsInterval, "Distance")
            finalScrns = os.path.join(os.path.join(outGDB, "XSEC_{}".format(Value)),
                                      "XSEC_{}_SCRNS_{}x".format(Value, ve))
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
        xsecMap.openView()

        if (scrnTable == "" and lithTable == ""):
            arcpy.management.Delete([zm_line, z_line, locPoints, eventTable, zBoreholes, bhLines, lithRoute])
        elif (scrnTable == "" and lithTable != ""):
            arcpy.management.Delete([zm_line, lithInterval, z_line, locPoints, eventTable, zBoreholes, bhLines, lithRoute])
        elif (scrnTable != "" and lithTable == ""):
            arcpy.management.Delete([zm_line, z_line, locPoints, eventTable, scrnsInterval, zBoreholes, bhLines, lithRoute])
        else:
            arcpy.management.Delete([zm_line, lithInterval, z_line, locPoints, eventTable, scrnsInterval, zBoreholes, bhLines, lithRoute])
            arcpy.management.SelectLayerByAttribute(newScrnTable, "CLEAR_SELECTION")
        if custom == "true":
            arcpy.management.Delete([newBhPoints,newScrnTable,newScrnTable])
        else:
            pass
        arcpy.management.DeleteField(lineLayer, checkField)
        if lithTable == "":
            pass
        else:
            xsecMap.addDataFromPath(finalLith)
        if scrnTable == "":
            pass
        else:
            xsecMap.addDataFromPath(finalScrns)
        # try:
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
        # except:
        #    AddMsgAndPrint("Cannot support Unique Symbology",1)
        #    pass
    except:
        AddMsgAndPrint("ERROR 006: Failed to clean up {}".format(os.path.basename(scratchDir)), 2)
        raise SystemError