"""
MGS_XSec_GridLines.py
Description: ArcToolbox tool script to create a set of cross-section grids defined by the end user.
             Specifically built for ArcGIS Pro software.
Requirements: python, ArcGIS Pro
Author: Matthew Bell, Michigan Geological Survey, matthew.e.bell@wmich.edu
Date: 3/19/2024

Last updated: 3/19/2024
"""

# Import Modules
# *******************************************************
import os
import arcpy
import numpy as np
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

# Vertical Exaggeration
ve = arcpy.GetParameterAsText(4)

# Grid line spacing option
grids = arcpy.ValueTable(4)
grids.loadFromString(arcpy.GetParameterAsText(5))

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
        prj.save()
        del inRows, labelRows
        arcpy.management.Delete([zm_line,z_line])
    except:
        AddMsgAndPrint("ERROR 018: Failed to clean up {}".format(os.path.basename(scratchDir)),2)
        raise SystemError