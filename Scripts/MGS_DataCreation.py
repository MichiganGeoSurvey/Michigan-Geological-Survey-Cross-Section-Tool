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

def appendFieldMappingInput(fieldMappings,oldTable,oldField,newField,newFieldType):
    # Add the input field for the given field name
    fieldMap = arcpy.FieldMap()
    fieldMap.addInputField(oldTable,oldField)
    name = fieldMap.outputField
    name.name,name.aliasName,name.type = newField,newField,newFieldType
    fieldMap.outputField = name
    # Add output field to field mapping objects
    fieldMappings.addFieldMap(fieldMap)

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

# Parameters
# *******************************************************
geologyLoc = arcpy.GetParameterAsText(0)

projectName = arcpy.GetParameterAsText(1)

pointsTable = arcpy.GetParameterAsText(2)

pointsShape = arcpy.GetParameterAsText(3)

aggTable = arcpy.GetParameterAsText(4)

# If the Wellogic lithology table has been exported out using the Geology Extraction script
accessory = arcpy.GetParameterAsText(5)

# The Excel table with the extra fields
accessTable = arcpy.GetParameterAsText(6)

featExtent = arcpy.GetParameterAsText(7)

prjDEM = arcpy.GetParameterAsText(8)

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
AddMsgAndPrint(msg="Scratch Geodatabase: {}".format(os.path.basename(scratchDir)),
               severity=0)

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
# First, let's add the domains to the geodatabase...
try:
    domainsNames = ["Color","Consistency","Drilling","FirstBDRK","GroupNames","LithAgg","LithAquifer","PrimaryLith",
                    "SecondaryLith","Simplified","WellStatus","TestMethod","Texture","Verification","WellAquifer",
                    "WellType","Age","CasingType"]
    desc = arcpy.Describe(geologyLoc)
    domains = desc.domains
    for domain in domains:
        if domain in domainsNames:
            try:
                arcpy.management.DeleteDomain(in_workspace=geologyLoc, domain_name=domain)
            except:
                AddMsgAndPrint("Domain in use. Passing to next step...")
                pass
        else:
            pass
    if "Color" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "Color", "Accepted color terms from Wellogic","TEXT", "CODED")
        colorDict = {"BLACK":"Black",
                     "BLACK & GRAY":"Black & Gray",
                     "BLUE":"Blue",
                     "BROWN":"Brown",
                     "CREAM": "Cream",
                     "GRAY":"Gray",
                     "GREEN":"Green",
                     "ORANGE":"Orange",
                     "PINK":"Pink",
                     "RED":"Red",
                     "RUST":"Rust",
                     "TAN":"Tan",
                     "WHITE":"White",
                     "BLACK & WHITE":"Black & White",
                     "DARK GRAY":"Dark Gray",
                     "GRAY & WHITE":"Gray & White",
                     "LIGHT BROWN":"Light Brown",
                     "LIGHT GRAY":"Light Gray",
                     "TAN & GRAY":"Tan & Gray",
                     "YELLOW":"Yellow"}
        for code in colorDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "Color", code, colorDict[code])
    if "Consistency" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "Consistency", "Accepted consistency terms from Wellogic", "TEXT", "CODED")
        consiDict = {"DENSE": "Dense",
                     "DRY": "Dry",
                     "GUMMY": "Gummy",
                     "KARST":"Karst",
                     "POROUS":"Porous",
                     "STRIPS":"Strips",
                     "CEMENTED":"Cemented",
                     "VERY HARD":"Very Hard",
                     "BROKEN":"Broken",
                     "FRACTURED":"Fractured",
                     "HEAVING/QUICK":"Heaving/Quick",
                     "STRINGERS":"Stringers",
                     "SWELLING":"Swelling",
                     "WATER BEARING":"Water Bearing",
                     "WEATHERED":"Weathered",
                     "WET/MOIST":"Wet/Moist",
                     "FIRM":"Firm",
                     "HARD":"Hard",
                     "SOFT":"Soft"}
        for code in consiDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "Consistency", code, consiDict[code])
    if "Drilling" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "Drilling", "Accepted drilling method terms from Wellogic", "TEXT",
                                      "CODED")
        drillDict = {"OTH":"Other",
                     "AUGBOR":"Auger/Bored",
                     "CABTOO":"Cable Tool",
                     "CASHAM":"Casing Hammer",
                     "DRIVEN":"Driven Hand",
                     "HOLROD":"Hollow Rod",
                     "JETTIN":"Jetted",
                     "TOOHAM":"Cable Tool w/Casing Hammer",
                     "ROTARY":"Mud Rotary",
                     "ROTHAM":"Rotary w/Casing Hammer",
                     "UNK":"Unknown"}
        for code in drillDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "Drilling", code, drillDict[code])
    if "FirstBDRK" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "FirstBDRK", "Definition if the unit is the first true bedrock unit in a borehole", "TEXT",
                                      "CODED")
        bdrkDict = {"YES":"Yes",
                    "NO":"No",
                    "NA":"Not Applicable"}
        for code in bdrkDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "FirstBDRK", code, bdrkDict[code])
    if "GroupNames" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "GroupNames","Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        groupDict = {"AGR":"Archean Granite & Gneissic",
                     "ANT":"Antrim Shale",
                     "AUM":"Archean Ultramafic",
                     "AVS":"Archean Volcanic & Sedimentary",
                     "BAY":"Bayport Limestone",
                     "BBF":"Bois Blanc Formation",
                     "BBG":"Burnt Bluff Group",
                     "BDG":"Badwater Greenstone",
                     "BED":"Bedford Shale",
                     "BER":"Berea Sandstone & Bedford Shale",
                     "BHD":"Big Hill Dolomite",
                     "BIF":"Bijiki Iron Formation",
                     "BIG":"Bass Island Group",
                     "BLS":"Bell Shale",
                     "BRG":"Black River Group",
                     "CHC":"Copper Harbor Conglomerate",
                     "CHO":"Chocolay Group",
                     "CHS":"Cabot Head Shale",
                     "CSM":"Collingwood Shale Member",
                     "CWT":"Coldwater Shale",
                     "DCF":"Dunn Creek Formation",
                     "DDL":"Dundee Limestone",
                     "DRG":"Detroit River Group",
                     "ELL":"Ellsworth Shale",
                     "ENG":"Engadine Group",
                     "EVC":"Emperor Volcanic Complex",
                     "FSS":"Freda Sandstone",
                     "GDQ":"Goodrich Quartzite",
                     "GIF":"Garden Island Formation",
                     "GLA":"Glacial Drift",
                     "GRF":"Grand River Formation",
                     "HEM":"Hemlock Formation",
                     "IIF":"Ironwood Iron Formation",
                     "INT":"Intrusive",
                     "JAC":"Jacobsville Sandstone",
                     "MAC":"Mackinac Breccia",
                     "MAR":"Marshall Formation",
                     "MCG":"Menominee & Chocolay Groups",
                     "MGF":"Michigamme Formation",
                     "MIF":"Michigan Formation",
                     "MND":"Manitoulin Dolomite",
                     "MQG":"Manistique Group",
                     "MUN":"Munising Formation",
                     "NIF":"Negaunee Iron Formation",
                     "NSF":"Nonesuch Formation",
                     "OBF":"Oak Bluff Formation",
                     "PAC":"Point Aux Chenes Shale",
                     "PAF":"Palms Formation",
                     "PDC":"Prairie Du Chien Group",
                     "PLV":"Portage Lake Volcanics",
                     "PRG":"Paint River Group",
                     "QUF":"Quinnesec Formation",
                     "QUS":"Queenston Shale",
                     "RAD":"Randville Dolomite",
                     "RBD":"Jurassic Red Beds",
                     "RIF":"Riverton Iron Formation",
                     "SAG":"Saginaw Formation",
                     "SAL":"Salina Group",
                     "SAQ":"Siamo Slate & Ajibik Quartzite",
                     "SCF":"Siemens Creek Formation",
                     "SID":"Saint Ignace Dolomite",
                     "SSS":"Sylvania Sandstone",
                     "STF":"Stonington Formation",
                     "SUN":"Sunbury Shale",
                     "TMP":"Trempealeau Formation",
                     "TRG":"Traverse Group",
                     "TRN":"Trenton Group",
                     "USM":"Utica Shale Member",
                     "PSS":"Parma Sandstone",
                     "GRG":"Grand Rapids Group",
                     "NSS":"Napolean Sandstone",
                     "SBL":"Squaw Bay Limestone",
                     "ALL":"Alpena Limestone",
                     "AMF":"Amherstburg Formation",
                     "LUF":"Lucas Formation",
                     "RCL":"Rogers City Limestone",
                     "NIA":"Niagara Group",
                     "CAG":"Cataract Group",
                     "RIG":"Richmond Group",
                     "GLM":"Glenwood Member",
                     "JSS":"Jordan Sandstone",
                     "SPS":"Saint Peter Sandstone",
                     "LOD":"Lodi Member",
                     "NRS":"New Richard Sandstone",
                     "OND":"Oneota Dolomite",
                     "SHD":"Shakopee Dolomite",
                     "SLM":"Saint Lawrence Member",
                     "DSS":"Dresbach Sandstone",
                     "ECM":"Eau Claire Member",
                     "FRS":"Franconia Sandstone",
                     "LSG":"Lake Superior Group",
                     "MSS":"Mount Simon Sandstone",
                     "PRE":"Precambrian Bedrock (Undefined)",
                     "UNK":"Unknown Group",
                     "AMA":"Amasa Formation"}
        for code in groupDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "GroupNames", code, groupDict[code])
    if "LithAgg" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "LithAgg", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        aggDict = {"UNK":"Unknown or No Record",
                   "BDRK":"Bedrock",
                   "CLAY":"Clay",
                   "CLSA":"Clay & Sand",
                   "DIAM":"Diamicton",
                   "TOPS":"Topsoil",
                   "GRAV":"Gravel",
                   "FSAN":"Fine Sand",
                   "ORGA":"Organics",
                   "SAND":"Sand",
                   "SAGR":"Sand & Gravel"}
        for code in aggDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "LithAgg", code, aggDict[code])
    if "LithAquifer" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "LithAquifer", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        lAQDict = {"D-AQ":"Drift: Aquifer Material",
                   "D-MAQ":"Drift: Marginal Aquifer Material",
                   "D-CM":"Drift: Confining Material",
                   "D-PCM":"Drift: Partially Confining Material",
                   "R-AQ":"Bedrock: Aquifer Material",
                   "R-MAQ":"Bedrock: Marginal Aquifer Material",
                   "R-CM":"Bedrock: Confining Material",
                   "R-PCM":"Bedrock: Partially Confining Material",
                   "D-NA":"Drift: Unknown Material",
                   "R-NA":"Bedrock: Unknown Material",
                   "U-NA":"Unknown: Unknown Material"}
        for code in lAQDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "LithAquifer", code, lAQDict[code])
    if "PrimaryLith" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "PrimaryLith", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        primDict = {"BASALT":"Basalt",
                    "BOULDERS":"Boulders",
                    "CLAY":"Clay",
                    "CLAY & BOULDERS":"Clay & Boulders",
                    "CLAY & COBBLES":"Clay & Cobbles",
                    "CLAY & GRAVEL":"Clay & Gravel",
                    "CLAY & SAND":"Clay & Sand",
                    "CLAY & SILT":"Clay & Silt",
                    "CLAY & STONES":"Clay & Stones",
                    "CLAY GRAVEL SAND":"Clay Gravel Sand",
                    "CLAY GRAVEL SILT":"Clay Gravel Silt",
                    "CLAY GRAVEL STONES":"Clay Gravel Stones",
                    "CLAY SAND GRAVEL":"Clay Sand Gravel",
                    "CLAY SAND SILT":"Clay Sand Silt",
                    "CLAY SILT GRAVEL":"Clay Silt Gravel",
                    "CLAY SILT SAND":"Clay Silt Sand",
                    "COAL":"Coal",
                    "COBBLES":"Cobbles",
                    "CONGLOMERATE":"Conglomerate",
                    "DEBRIS":"Debris",
                    "DOLOMITE":"Dolomite",
                    "DOLOMITE & LIMESTONE":"Dolomite & Limestone",
                    "DOLOMITE & SANDSTONE":"Dolomite & Sandstone",
                    "DOLOMITE & SHALE":"Dolomite & Shale",
                    "DRY HOLE":"Dry Hole",
                    "GRANITE":"Granite",
                    "GRAVEL":"Gravel",
                    "GRAVEL & BOULDERS":"Gravel & Boulders",
                    "GRAVEL & CLAY":"Gravel & Clay",
                    "GRAVEL & COBBLES":"Gravel & Cobbles",
                    "GRAVEL & SAND":"Gravel & Sand",
                    "GRAVEL & SILT":"Gravel & Silt",
                    "GRAVEL & STONES":"Gravel & Stones",
                    "GRAVEL CLAY SAND":"Gravel Clay Sand",
                    "GRAVEL CLAY SILT":"Gravel Clay Silt",
                    "GRAVEL SAND CLAY":"Gravel Sand Clay",
                    "GRAVEL SAND SILT":"Gravel Sand Silt",
                    "GRAVEL SILT CLAY":"Gravel Silt Clay",
                    "GRAVEL SILT SAND":"Gravel Silt Sand",
                    "GREENSTONE":"Greenstone",
                    "GYPSUM":"Gypsum",
                    "HARDPAN":"Hardpan",
                    "INTERVAL NOT SAMPLED":"Interval Not Sampled",
                    "IRON FORMATION":"Iron Formation",
                    "LIMESTONE":"Limestone",
                    "LIMESTONE & DOLOMITE":"Limestone & Dolomite",
                    "LIMESTONE & SANDSTONE":"Limestone & Sandstone",
                    "LIMESTONE & SHALE":"Limestone & Shale",
                    "LITHOLOGY UNKNOWN":"Lithology Unknown",
                    "LOAM":"Loam",
                    "MARL":"Marl",
                    "MUCK":"Muck",
                    "MUD":"Mud",
                    "NO LITHOLOGY INFORMATION":"No Lithology Information",
                    "NO LOG":"No Log",
                    "PEAT":"Peat",
                    "QUARTZ":"Quartz",
                    "QUARTZITE":"Quartzite",
                    "SAND":"Sand",
                    "SAND & BOULDERS":"Sand & Boulders",
                    "SAND & CLAY":"Sand & Clay",
                    "SAND & COBBLES":"Sand & Cobbles",
                    "SAND & GRAVEL":"Sand & Gravel",
                    "SAND & SILT":"Sand & Silt",
                    "SAND & STONES":"Sand & Stones",
                    "SAND CLAY GRAVEL":"Sand Clay Gravel",
                    "SAND CLAY SILT":"Sand Clay Silt",
                    "SAND GRAVEL CLAY":"Sand Gravel Clay",
                    "SAND GRAVEL SILT":"Sand Gravel Silt",
                    "SAND SILT CLAY":"Sand Silt Clay",
                    "SAND SILT GRAVEL":"Sand Silt Gravel",
                    "SANDSTONE":"Sandstone",
                    "SANDSTONE & LIMESTONE":"Sandstone & Limestone",
                    "SANDSTONE & SHALE":"Sandstone & Shale",
                    "SCHIST":"Schist",
                    "SEE COMMENTS":"See Comments",
                    "SHALE":"Shale",
                    "SHALE & COAL":"Shale & Coal",
                    "SHALE & LIMESTONE":"Shale & Limestone",
                    "SHALE & SANDSTONE":"Shale & Sandstone",
                    "SHALE SANDSTONE LIMESTONE":"Shale Sandstone Limestone",
                    "SILT":"Silt",
                    "SILT & BOULDERS":"Silt & Boulders",
                    "SILT & CLAY":"Silt & Clay",
                    "SILT & COBBLES":"Silt & Cobbles",
                    "SILT & GRAVEL":"Silt & Gravel",
                    "SILT & SAND":"Silt & Sand",
                    "SILT & STONES":"Silt & Stones",
                    "SILT CLAY GRAVEL":"Silt Clay Gravel",
                    "SILT CLAY SAND":"Silt Clay Sand",
                    "SILT GRAVEL CLAY":"Silt Gravel Clay",
                    "SILT GRAVEL SAND":"Silt Gravel Sand",
                    "SILT SAND CLAY":"Silt Sand Clay",
                    "SILT SAND GRAVEL":"Silt Sand Gravel",
                    "SLATE":"Slate",
                    "SOAPSTONE (TALC)":"Soapstone (Talc)",
                    "STONES":"Stones",
                    "TOPSOIL":"Topsoil",
                    "UNIDENTIFIED CONSOLIDATED FM":"Unidentified Consolidated Fm",
                    "UKNOWN":"Unknown",
                    "VOID":"Void"}
        for code in primDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "PrimaryLith", code, primDict[code])
    if "SecondaryLith" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "SecondaryLith", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        secDict = {"CLAYEY":"Clayey",
                   "DOLOMITIC":"Dolomitic",
                   "FILL":"Fill",
                   "GRAVELY":"Gravely",
                   "ORGANIC":"Organic",
                   "SANDY":"Sandy",
                   "SILTY":"Silty",
                   "STONEY":"Stoney",
                   "W/BOULDERS":"With Boulders",
                   "W/CLAY":"With Clay",
                   "W/COAL":"With Coal",
                   "W/COBBLES":"With Cobbles",
                   "W/DOLOMITE":"With Dolomite",
                   "W/GRAVEL":"With Gravel",
                   "W/GYPSUM":"With Gypsum",
                   "W/LIMESTONE":"With Limestone",
                   "W/PYRITE":"With Pyrite",
                   "W/SAND":"With Sand",
                   "W/SANDSTONE":"With Sandstone",
                   "W/SHALE":"With Shale",
                   "W/SILT":"With Silt",
                   "W/STONES":"With Stones",
                   "WOOD":"Wood"}
        for code in secDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "SecondaryLith", code, secDict[code])
    if "Simplified" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "Simplified", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        simpDict = {"UNK":"Unknown Sediment Type",
                    "FINE":"Fine-Grained Sediments",
                    "COARSE":"Coarse-Grained Sediments",
                    "MIXED":"Mixed-Grained Sediments",
                    "ORGANIC":"Organic Sediments",
                    "BEDROCK":"Bedrock Unit"}
        for code in simpDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "Simplified", code, simpDict[code])
    if "WellStatus" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "WellStatus", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        statDict = {"OTH":"Other",
                    "ACT":"Active",
                    "INACT":"Inactive",
                    "PLU":"Plugged/Abandoned",
                    "UNK":"Unknown"}
        for code in statDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "WellStatus", code, statDict[code])
    if "TestMethod" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "TestMethod", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        testDict = {"UNK":"Unknown",
                    "OTH":"Other",
                    "AIR":"Air",
                    "BAIL":"Bailer",
                    "PLUGR":"Plunger",
                    "TSTPUM":"Test Pump"}
        for code in testDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "TestMethod", code, testDict[code])
    if "Texture" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "Texture", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        textDict = {"COARSE":"Coarse",
                    "FINE":"Fine",
                    "MEDIUM":"Medium",
                    "FINE TO COARSE":"Fine To Coarse",
                    "FINE TO MEDIUM":"Fine To Medium",
                    "MEDIUM TO COARSE":"Medium To Coarse",
                    "VERY COARSE":"Very Coarse",
                    "VERY FINE":"Very Fine",
                    "VERY FINE-COARSE":"Very Fine To Coarse",
                    "VERY FINE-FINE":"Very Fine to Fine",
                    "VERY FINE-MEDIUM":"Very Fine To Medium"}
        for code in textDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "Texture", code, textDict[code])
    if "Verification" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "Verification", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        verDict = {"Y":"Yes",
                   "N":"No"}
        for code in verDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "Verification", code, verDict[code])
    if "WellAquifer" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "WellAquifer", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        wAQDict = {"DRIFT":"Drift Aquifer",
                   "ROCK":"Bedrock Aquifer",
                   "UNK":"Unknown Aquifer",
                   "DRYHOL":"Dry Hole"}
        for code in wAQDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "WellAquifer", code, wAQDict[code])
    if "WellType" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "WellType", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        wellTDict = {"OTH":"Other",
                     "HEATP":"Heat Pump",
                     "HOSHLD":"Household",
                     "INDUS":"Industrial",
                     "IRRI":"Irrigation",
                     "TESTW":"Test Well",
                     "TY1PU":"Type I Public Supply",
                     "TY2PU":"Type II Public Supply",
                     "TY3PU":"Type III Public Supply",
                     "HEATRE":"Heat Pump: Return",
                     "HEATSU":"Heat Pump: Supply"}
        for code in wellTDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "WellType", code, wellTDict[code])
    if "Age" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "Age", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        ageDict = {"UNK":"Unknown Age",
                   "PH-CEN-PLEI":"Pleistocene",
                   "PH-MES-MJUR":"Middle Jurassic",
                   "PH-PAL-LPEN":"Late Pennsylvanian",
                   "PH-PAL-EPEN":"Early Pennsylvanian",
                   "PH-PAL-EPLM":"Early Pennsylvanian to Late Mississippian",
                   "PH-PAL-LMIS":"Late Mississippian",
                   "PH-PAL-EMIS":"Late Mississippian",
                   "PH-PAL-LDEV":"Late Devonian",
                   "PH-PAL-MDLD":"Late to Middle Devonian",
                   "PH-PAL-MDEV":"Middle Devonian",
                   "PH-PAL-EDEV":"Early Devonian",
                   "PH-PAL-LSIL":"Late Silurian",
                   "PH-PAL-MSIL":"Middle Silurian",
                   "PH-PAL-ESIL":"Early Silurian",
                   "PH-PAL-LORD":"Late Ordovician",
                   "PH-PAL-MORD":"Middle Ordovician",
                   "PH-PAL-EORD":"Early Ordovician",
                   "PH-PAL-LCAM":"Late Cambrian",
                   "PC-PRO-EARL":"Early Proterozoic",
                   "PC-PRO-MIDL":"Middle Proterozoic",
                   "PC":"Precambrian Age",
                   "PC-ARC-EARL":"Early Archean",
                   "PC-ARC-LATE":"Late Archean",
                   "PC-PRO-MESO":"Mesoproterozoic",
                   "PH-PAL-MDLS":"Middle Devonian to Late Silurian"}
        for code in ageDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "Age", code, ageDict[code])
    if "CasingType" in domains:
        pass
    else:
        arcpy.management.CreateDomain(geologyLoc, "CasingType", "Group names for all formations found in Michigan", "TEXT",
                                      "CODED")
        caseDict = {"OTH":"Other",
                    "UNK":"Unknown",
                    "PVCPLA":"PVC Plastic",
                    "STEBLA":"Steel: Black",
                    "STEGAL":"Steel: Galvanized",
                    "STEUNK":"Steel: Unknown",
                    "NONE":"No Casing"}
        for code in caseDict:
            arcpy.management.AddCodedValueToDomain(geologyLoc, "CasingType", code, caseDict[code])
except:
    AddMsgAndPrint("ERROR 001: Failed to add domains",2)
    raise SystemError

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
    if accessory == "true":
        arcpy.management.AddField(in_table=lithTable, field_name="RELATE", field_type="TEXT", field_length=255)
        arcpy.management.AddField(in_table=lithTable, field_name="THIRD_DESC", field_type="TEXT", field_length=255)
        arcpy.management.AddField(in_table=lithTable, field_name="GROUP_NAME", field_type="TEXT", field_length=255)
        arcpy.management.AddField(in_table=lithTable, field_name="COMMENTS", field_type="TEXT", field_length=10000)
    else:
        pass
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

    if accessory == "true":
        extraTable = os.path.join(scratchDir,os.path.splitext(os.path.basename(accessTable))[0])
        arcpy.conversion.ExcelToTable(Input_Excel_File=accessTable,
                                      Output_Table=extraTable)
        arcpy.management.AddField(in_table=extraTable, field_name="RELATE", field_type="TEXT", field_length=255)
        arcpy.management.CalculateField(in_table=extraTable,
                                        field="RELATE",
                                        expression='"{}_{}".format(!WELLID!,int(!SEQ_NUM!))')
        arcpy.management.CalculateField(in_table=lithTable,
                                        field="RELATE",
                                        expression='"{}_{}".format(!WELLID!,int(!SEQ_NUM!))')
        arcpy.management.JoinField(
            in_data=lithTable, in_field="RELATE", join_table=extraTable, join_field="RELATE",
            fields="FORMATION;GEO_COMMENTS")
        with arcpy.da.UpdateCursor(lithTable,["FORMATION","GEO_COMMENTS","THIRD_DESC","GROUP_NAME","COMMENTS","COLOR","TEXTURE","CON","SEC_DESC"]) as cursor:
            for row in cursor:
                if row[1] is not None:
                    row[4] = row[1]
                cursor.updateRow(row)
                if row[0] in textGroup:
                    row[6] = row[0].upper()
                elif row[0] in conGroup:
                    row[7] = row[0].upper()
                elif row[0] in secGroup:
                    if row[8] is None:
                        row[8] = row[0].upper()
                    else:
                        row[2] = row[0].upper()
                elif row[0] in colorGroup:
                    if row[5] == None:
                        row[5] = row[0].upper()
                    else:
                        pass
                elif row[0] in groupGroup:
                    if row[0] == "Alpena Ls":
                        row[3] = "ALL"
                    elif row[0] == "Antrim Shale":
                        row[3] = "ANT"
                    elif row[0] == "Bass Island Group":
                        row[3] = "BIG"
                    elif row[0] == "Bayport Ls":
                        row[3] = "BAY"
                    elif row[0] == "Bedford Shale":
                        row[3] = "BED"
                    elif row[0] == "Bell Shale":
                        row[3] = "BLS"
                    elif row[0] == "Berea Ss":
                        row[3] = "BER"
                    elif row[0] == "Black River Group":
                        row[3] = "BRG"
                    elif row[0] == "Bois Blanc Fm":
                        row[3] = "BBF"
                    elif row[0] == "Burnt Bluff Group":
                        row[3] = "BBG"
                    elif row[0] == "Cabot Head Shale":
                        row[3] = "CHS"
                    elif row[0] == "Cataract Group":
                        row[3] = "CAG"
                    elif row[0] == "Coldwater Shale":
                        row[3] = "CWT"
                    elif row[0] == "Collingwood Shale":
                        row[3] = "CSM"
                    elif row[0] == "Detroit River Group":
                        row[3] = "DRG"
                    elif row[0] == "Dresbach Ss":
                        row[3] = "DSS"
                    elif row[0] == "Dundee Ls":
                        row[3] = "DDL"
                    elif row[0] == "Eau Claire Member":
                        row[3] = "ECM"
                    elif row[0] == "Ellsworth Shale":
                        row[3] = "ELL"
                    elif row[0] == "Engadine Dol":
                        row[3] = "ENG"
                    elif row[0] == "Franconia Ss":
                        row[3] = "FRS"
                    elif row[0] == "Freda Ss":
                        row[3] = "FSS"
                    elif row[0] == "Garden Island Fm":
                        row[3] = "GIF"
                    elif row[0] == "Glenwood Member":
                        row[3] = "GLM"
                    elif row[0] == "Grand Rapids Group":
                        row[3] = "GRG"
                    elif row[0] == "Grand River Fm":
                        row[3] = "GRF"
                    elif row[0] == "Jacobsville Ss":
                        row[3] = "JAC"
                    elif row[0] == "Jordan Ss":
                        row[3] = "JSS"
                    elif row[0] == "Lake Superior Group":
                        row[3] = "LSG"
                    elif row[0] == "Lodi Member":
                        row[3] = "LOD"
                    elif row[0] == "Lucas Fm":
                        row[3] = "LUF"
                    elif row[0] == "Manistique Group":
                        row[3] = "MQG"
                    elif row[0] == "Manitoulin Dol":
                        row[3] = "MND"
                    elif row[0] == "Marshall Ss":
                        row[3] = "MAR"
                    elif row[0] == "Michigammee Fm":
                        row[3] = "MGF"
                    elif row[0] == "Michigan Fm":
                        row[3] = "MIF"
                    elif row[0] == "Mt. Simon Ss":
                        row[3] = "MSS"
                    elif row[0] == "Napolean Ss":
                        row[3] = "NSS"
                    elif row[0] == "New Richmond Ss":
                        row[3] = "NRS"
                    elif row[0] == "Niagara Group":
                        row[3] = "NIA"
                    elif row[0] == "Nonesuch Shale":
                        row[3] = "NSF"
                    elif row[0] == "Oneota Dol":
                        row[3] = "OND"
                    elif row[0] == "Parma Ss":
                        row[3] = "PSS"
                    elif row[0] == "Prairie Du Chien Group":
                        row[3] = "PDC"
                    elif row[0] == "Precambrian":
                        row[3] = "PRE"
                    elif row[0] == "Queenston Shale":
                        row[3] = "QUS"
                    elif row[0] == "Red Beds":
                        row[3] = "RBD"
                    elif row[0] == "Richmond Group":
                        row[3] = "RIG"
                    elif row[0] == "Rogers City Ls":
                        row[3] = "RCL"
                    elif row[0] == "Saginaw Fm":
                        row[3] = "SAG"
                    elif row[0] == "Salina Group":
                        row[3] = "SAL"
                    elif row[0] == "Shakopee Dol":
                        row[3] = "SHD"
                    elif row[0] == "Squaw Bay Ls":
                        row[3] = "SBL"
                    elif row[0] == "St. Lawrence Member":
                        row[3] = "SLM"
                    elif row[0] == "St. Peter Ss":
                        row[3] = "SPS"
                    elif row[0] == "Sylvania Ss":
                        row[3] = "SSS"
                    elif row[0] == "Traverse Group":
                        row[3] = "TRG"
                    elif row[0] == "Trempealeau Fm":
                        row[3] = "TMP"
                    elif row[0] == "Trenton Group":
                        row[3] = "TRN"
                    elif row[0] == "Utica Shale":
                        row[3] = "USM"
                    else:
                        row[3] = None
                else:
                    pass
                cursor.updateRow(row)
            del row
            del cursor
        arcpy.management.DeleteField(lithTable,["FORMATION","GEO_COMMENTS"])
    else:
        pass
except:
    AddMsgAndPrint("ERROR 002: Failed to format old table",2)
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
    AddMsgAndPrint("ERROR 003: Failed to make new table with standard fields",2)
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
    if accessory == "true":
        appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="THIRD_DESC", newField="THIRD_LITH",
                                newFieldType="TEXT")
        appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="GROUP_NAME", newField="GROUP_NAME",
                                newFieldType="TEXT")
        appendFieldMappingInput(fieldMappings=lithMappings, oldTable=lithTable, oldField="COMMENTS", newField="GEO_COMMENTS",
                                newFieldType="TEXT")
    else:
        pass
    arcpy.management.Append(lithTable, newLithTable, "NO_TEST", lithMappings, "")
except:
    AddMsgAndPrint("ERROR 004: Failed to append old data into the new table",2)
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
    AddMsgAndPrint("ERROR 005: Failed to fill in empty fields",2)
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
    AddMsgAndPrint("ERROR 006: Failed to export 'no record' and 'first bedrock' lithology tables",2)
    raise SystemError

try:
    AddMsgAndPrint("Adding tables and cleaning scratch geodatabase...")
    pm = prj.activeMap
    pm.addDataFromPath(newLithTable)
    pm.addDataFromPath(bdrkLithTable)
    prj.save()
    arcpy.management.Delete(lithTable)
except:
    AddMsgAndPrint("ERROR 007: Failed to import lithology tables and/or failed to clean geodatabase",2)
    raise SystemError

arcpy.AddMessage('_____________________________')
arcpy.AddMessage("BEGIN FORMATTING THE WATER WELL POINTS FEATURE CLASS...")
try:
    wwName = projectName + "_WW_Points"
    AddMsgAndPrint("Extracting elevation data to {}...".format(os.path.splitext(os.path.basename(pointsShape))[0].replace(" ","_")))
    if arcpy.Describe(pointsShape).spatialReference == "GCS_WGS_1984":
        eventProject = os.path.join(scratchDir, os.path.splitext(os.path.basename(pointsShape))[0].replace(" ","_") + '_project')
        arcpy.AddMessage("- Projecting shapefile to NAD 1983 Hotine projection")
        arcpy.management.Project(pointsShape, eventProject, "", "WGS_1984_(ITRF00)_To_NAD_1983",
                                 "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984',SPHEROID['WGS_1984',6378137.0,298.257223563]],PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]",
                                 "NO_PRESERVE_SHAPE", "", "NO_VERTICAL")
        arcpy.management.SelectLayerByLocation(eventProject, 'INTERSECT', featExtent, None, 'NEW_SELECTION', '')
        eventExtract = os.path.join(scratchDir, os.path.splitext(os.path.basename(pointsShape))[0].replace(" ","_") + '_extract')
        arcpy.sa.ExtractValuesToPoints(eventProject,prjDEM,eventExtract,"","")
    else:
        arcpy.management.SelectLayerByLocation(pointsShape, 'INTERSECT', featExtent, None, 'NEW_SELECTION', '')
        eventExtract = os.path.join(scratchDir, os.path.splitext(os.path.basename(pointsShape))[0].replace(" ","_") + '_extract')
        arcpy.sa.ExtractValuesToPoints(pointsShape, prjDEM, eventExtract, "", "")
except:
    AddMsgAndPrint("ERROR 008: Failed to extract elevation values to {}".format(os.path.splitext(os.path.basename(pointsShape))[0].replace(" ","_")),2)
    AddMsgAndPrint("Error is likely too many locations outside of the elevation DEM.")
    raise SystemError

try:
    AddMsgAndPrint("- Formatting {} to prepare for appending...".format(os.path.splitext(os.path.basename(eventExtract))[0]))
    with arcpy.da.UpdateCursor(eventExtract, "RASTERVALU") as cursor:
        for row in cursor:
            if row[0] == None:
                cursor.deleteRow()
        del row, cursor
except:
    AddMsgAndPrint("ERROR 009: Failed to format {}".format(os.path.splitext(os.path.basename(eventExtract))[0]),2)
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
    AddMsgAndPrint("ERROR: Failed to create final dataset template",2)
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
    AddMsgAndPrint("ERROR 011: Failed to append {} to {}".format(os.path.splitext(os.path.basename(eventExtract))[0],os.path.splitext(os.path.basename(outWWpoints))[0]),2)
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
    AddMsgAndPrint("ERROR 012: Failed to format new points table",2)
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
    AddMsgAndPrint("ERROR 013: Failed to add data into the respective maps",2)
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
    AddMsgAndPrint("ERROR 014: Failed to copy {} for editing".format(os.path.splitext(os.path.basename(outWWpoints))[0]),2)
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
    AddMsgAndPrint("ERROR 015: Failed to add tables and clean geodatabase for water well points",2)
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
    AddMsgAndPrint("ERROR 016: Failed to extract screen information",2)
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
    AddMsgAndPrint("ERROR 017: Failed to create the screens table",2)
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
    AddMsgAndPrint("ERROR 018: Failed to append event data to permanent data table",2)
    raise SystemError

try:
    arcpy.management.CalculateField(tableScr, "SEQ_NUM", 1, "PYTHON3", "")
    arcpy.management.CalculateField(tableScr, "THICKNESS", "!DEPTH_BOT! - !DEPTH_TOP!", "PYTHON3", "")
    arcpy.management.CalculateField(tableScr, "STRAT", "\"Screen\"", "PYTHON3", "")
except:
    AddMsgAndPrint("ERROR 019: Failed to format empty fields in {}".format(os.path.splitext(os.path.basename(tableScr))[0]),2)
    raise SystemError
try:
    arcpy.AddMessage("Adding tables and cleaning scratch geodatabase...")
    pm = prj.activeMap
    pm.addDataFromPath(tableScr)
    prj.save()
    arcpy.management.Delete([eventScreens,outScreen])
except:
    AddMsgAndPrint("ERROR 020: Failed to add tables and clean geodatabase for screens",2)
    raise SystemError