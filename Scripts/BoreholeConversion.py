import arcpy
import os
import csv
import pandas as pd

# Functions
# *************************************************
def testanddelete(fc):
       if arcpy.Exists(fc):
              arcpy.management.Delete(fc)


# Parameters
# *************************************************
lith_table = arcpy.GetParameterAsText(0)
gsa_table = arcpy.GetParameterAsText(1)
output_folder = arcpy.GetParameterAsText(2)
borehole_id = arcpy.GetParameterAsText(3)

# Local Variables
# *************************************************



# Begin
# *************************************************
# Environmental Parameters
arcpy.env.overwriteOutput = True
scratchDir = arcpy.env.scratchWorkspace
arcpy.env.workspace = scratchDir
arcpy.AddMessage("Scratch Space: " + os.path.splitext(os.path.basename(scratchDir))[0])

#Selecting boreholes to be exported
arcpy.AddMessage(borehole_id.replace("BoreholeID = ","").replace("'",""))
lith_sel = arcpy.management.SelectLayerByAttribute(in_layer_or_view = lith_table,
                                                        selection_type = "NEW_SELECTION",
                                                        where_clause = borehole_id,
                                                        invert_where_clause ="")

gsa_sel = arcpy.management.SelectLayerByAttribute(in_layer_or_view = gsa_table,
                                                        selection_type = "NEW_SELECTION",
                                                        where_clause = borehole_id,
                                                        invert_where_clause ="")
#Creating temporary tables
scratch_lith = os.path.join(scratchDir, "Scratch_Lith")
arcpy.management.CopyRows(lith_sel,scratch_lith)
arcpy.management.AddField(in_table = scratch_lith,
                          field_name = "interval",
                          field_type = "TEXT",
                          field_length = 255)
arcpy.management.AddField(in_table = scratch_lith,
                          field_name = "description",
                          field_type = "TEXT",
                          field_length = 10000)


#Concatenation expressions for lithology
desc_expression = ("""var sec = [$feature.texture_mod,$feature.lith_mod,$feature.sorting,$feature.angular,$feature.formation,$feature.notes];
var color = [$feature.primary_color,$feature.munsell_code];
var sec_desc = [];
var color_desc = [];
for (var i in sec){
    if (!IsEmpty(sec[i])){
        sec_desc[Count(sec_desc)] = Lower(sec[i]);
    }
}
for (var i in color){
    if (!IsEmpty(color[i])){
        color_desc[Count(color_desc)] = color[i];
    }
}
return IIf((Count(color_desc)==0)&&(Count(sec_desc)==0),Upper($feature.prim_material),
IIf((Count(color_desc)==0)&&(Count(sec_desc)!=0),(Upper($feature.prim_material) + ": " + Concatenate(sec_desc,", ")),
IIf((Count(color_desc)!=0)&&(Count(sec_desc)==0),(Upper($feature.prim_material) + ": " + Concatenate(color_desc,", ")),(Upper($feature.prim_material) + ": " + Concatenate(sec_desc,", ") + "; " + Concatenate(color_desc,", ")))));""")

arcpy.management.CalculateField(in_table = scratch_lith,
                                field = "description",
                                expression = desc_expression,
                                expression_type = "ARCADE")

arcpy.management.CalculateField(in_table = scratch_lith,
                                field = "interval",
                                expression = "str(!top_depth!)+'-'+str(!btm_depth!)+'ft'")

# Defining Name for output CSV files
output_csv_lith = os.path.join(output_folder, "WellCAD_Lith.csv")
output_csv_gsa = os.path.join(output_folder, "WellCADGSA.csv")

#Converting ArcTables to previously defined CSVs
arcpy.conversion.ExportTable(scratch_lith, output_csv_lith)
arcpy.conversion.ExportTable(gsa_sel, output_csv_gsa)

#Create Pandas dataframe to read data
df_lith = pd.read_csv(output_csv_lith)
df_gsa = pd.read_csv(output_csv_gsa)


# Define the fields you want to include in the output CSV files
lith_transfer_fields = ["top_depth","btm_depth","interval","lith_symbology","description"]
gsa_transfer_fields = ["depth_ft","sample_gravel","sandfrac_vc","sandfrac_c","sandfrac_m","sandfrac_f","sandfrac_vf",
                       "sample_silt","sample_clay"]

#Define columns for lith table
df_lith.rename(columns = {"prim_material":"lith_symbology"},
               inplace = True)
df_lith.columns
df_lith = df_lith[lith_transfer_fields]
df_lith.insert(3,"top_depth2","",True)
df_lith.insert(4,"btm_depth2","",True)
df_lith.insert(6,"top_depth3","",True)
df_lith.insert(7,"btm_depth3","",True)
df_lith["top_depth2"] = df_lith["top_depth"].apply(lambda x: x)
df_lith["top_depth3"] = df_lith["top_depth"].apply(lambda x: x)
df_lith["btm_depth2"] = df_lith["btm_depth"].apply(lambda x: x)
df_lith["btm_depth3"] = df_lith["btm_depth"].apply(lambda x: x)

df_gsa = df_gsa[gsa_transfer_fields]


#Write CSV output
df_lith.to_csv(os.path.join(output_folder, "{}_WellCAD_Lith.csv".format(borehole_id.replace("BoreholeID = ","").replace("'",""))),index=False)
df_gsa.to_csv(os.path.join(output_folder, "{}_WellCAD_GSA.csv".format(borehole_id.replace("BoreholeID = ","").replace("'",""))),index=False)


# Print a message
arcpy.AddMessage(f"Conversion completed. CSV files saved at:\n{output_csv_lith}\n{output_csv_gsa}")