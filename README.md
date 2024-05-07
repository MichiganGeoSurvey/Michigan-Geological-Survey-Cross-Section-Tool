# Michigan Geological Survey: Cross-Section Tool Box for ArcGIS Pro
 The following tool was developed to automate the process of creating GIS layers for groundwater analysis, as well as provide a resource for generating cross-section views of geologic data in ArcGIS Pro. The implementation of the tools is as follows:
1. Creates a project area from a DEM and acquires a range of Michigan specific datasets for use in maps and cross-sections (Not applicable for other states).
2. Reformats water well datasets to be used in analyses.
3. Generates groundwater surface profiles.
4. Generates cross-section views of multiple lines that display the following:
   1. Borehole depths and lithologies.
   2. Screened intervals.
   3. Surface topography profiles.
   4. Bedrock topography profiles.
   5. Groundwater topography profiles.
   6. Reference grid.
5. Generate individual portions of the full cross-section tool to make adjustments.

---

### **WHAT IS INCLUDED**

**MGS_XSEC_TOOLS_vX.atbx**  

ArcGIS Pro toolbox containing all available MGS custom tools which include: 

*Cross-Section Tools*
  - Cross-Section Tools (All Steps)  
  Function: Combines all cross-section tools listed below in addition to a topographic surface profile.  
  - Cross-Section Tools (Borehole Sticks)  
  Function: Creates borehole sticks and screens for cross-sections.  
  - Cross-Section Tools (Gridline Creation)  
  Function: Creates a reference grid that extends to the boundaries of the input cross-sections.  
  - Cross-Section Tools (Segment Profiles)  
  Function: Creates surface profiles from bedrock and/or groundwater surface rasters.

*Data Formatting Tools*  
  - Data Formatting
  Function: Converts Wellogic water well data into a usable format for the cross-section tools  
  - GWL Raster Creation  
  Function: Creates groundwater surface rasters from water well data
  - Project Creation
  Function: Sets up a Wellogic water well project (MICHIGAN ONLY) around a given area to be used for maps and cross-sections.

**ArcGIS_Pro_TrainingDocument_XSEC_ONLY_YYYYMMDD.pdf**

  This is an instructional document for creating cross-sections only. Applicable for most users.

**ArcGIS_Pro_TrainingDocument_WellogicData_YYYYMMDD.pdf**  
  
  This is an instructional document designed for creating projects out of data from the Wellogic water well database.

 **Templates**  

  This folder incudes several formatting and symbology files for symbolizing several of the toolboxes outputs which include:

  - GWL Colors  
  Function: Folder containing several symbologies for different well types and time periods of groundwater levels  
  - Cross_Section_CoordinateSystem.prj  
  Function: Custom coordinate system for the cross-sections. This is hard-coded into the scripts and not required to run them but it may be necessary to add additional layers to the cross-section that were not created using the MGS toolbox  
  - LithologyClasses_YYYYMMDD.xlsx  
  Function: MGS's system for simplyfying Wellogic data into aggregated lithology classes. This file is required for running both the *Project Creation* tool and the *Data Reformatting* tool  
  - LithSticks_UPDATE_YYYYMMDD.lyrx  
  Function: Symbology for borehole lines (Polylines)
  - LithSticks_Polygons_YYYYMMDD.lyrx  
  Function: Symbology for borehole lines (Polygons)
  - NAD_1983_Hotine_Oblique_Mercator_Azimuth_Natural_Origin.prj  
  Function: Custom coordinate system for the project creation tool. This is hard-coded into the scripts and not required to run them but it may be necessary to add additional layers to the project that were not created using the MGS toolbox
  - ScreensPolygon_YYYYMMDD.lyrx  
  Function: Symbology for screen lines (Polygon)
  - ScreensSticks_UPDATED_YYYYMMDD.lyrx  
  Function: Symbology for screen lines (Polyline)


**README.md**  

  Document outlining basic information about the tools, their limitations and an End-User License Agreement (EULA).  

**LICENSE.txt**

  Attribution-NonCommercial-ShareAlike 4.0 International license information applicable to all properties distributed through the MichiganGeoSurvey GitHub page.
  
---

### **SAMPLE PROJECT**

We have provided a sample project created from Wellogic water well data as an example of what a completed project, the outputs, and potential layouts look like. This project was created using the Project Creation Tool and the Cross-Section Tool (All Steps). The project can be found at the Google Drive link [here](https://drive.google.com/file/d/1JNzOIs55Wu8ZSHcnO1A49oCTzS-EoyP7/view?usp=sharing) (Approximate size: 800mb)

---

### **IMPORTANT NOTES**

The processing time for all of the tools is directly related to the size of the project, size, and number of cross-section lines. Large projects with many cross-sections can take hours or even days to complete. Clipping both your water well points and lithology tables to only include the wells that are relevant to your cross-sections will significantly reduce processing time. This run-time issue will hopefully be reduced in the future through tool optimizations and updates. 

Example (Medium):  
Cross-Section All Steps Tool  
Area: ~100 square miles  
Cross Sections: 5 (ranging from 4 to 10 miles long)  
Total Runtime: ~30 minutes to 1 hour  

Example (Very Large):  
Cross-Section All Steps Tool  
Area: ~1500 square miles  
Cross-section: 58 (ranging from 6-30+ miles long)  
Total Runtime: 3 Days 16 Hours  

---

### **KNOWN ISSUES**

Both the Cross-Section (All Steps) and the Borehole Sticks tools take the longest on the "Segmenting Profiles" portion but will sometimes freeze there. It may seem stuck during this phase but it can also just take a long time to move forward. Give it a half hour to 2 hours per cross-section line before cancelling and trying again.

---

### **SPECIAL THANKS**

Special thank you to Evan Thoms and the rest of USGS for providing the base work that was used to create these tools.
Evan Thom’s [GitHub Page](https://github.com/ethoms-usgs)

---

### **End-User License Agreement (EULA)**

By using this code, you are agreeing to the following terms and conditions:

1. **No Commercial Use:** This software, including all associated scripts and tools, is provided solely for non-commercial, experimental, and educational purposes. It is expressly prohibited to use this software or any derived works for any commercial purposes, including but not limited to, selling, licensing, or incorporating into any commercial product or service without explicit written consent from MGS. This software is provided free of charge and may not be sold, licensed, or used for any commercial purposes without explicit written consent from MGS.

2. **Limited Warranty:** The software is provided "as is," without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. MGS makes no warranty that the software will be error-free or that errors will be corrected. You acknowledge that your use of the software may result in unexpected or undesirable outcomes, and you assume sole responsibility and risk for your use of the software and the results obtained.

3. **No Guarantee of Accuracy:** MGS cannot guarantee the accuracy, reliability, or completeness of the output generated by the software tools. You acknowledge that the software tools may produce varying results depending on factors such as input data quality, software configuration, and environmental conditions. It is your responsibility to verify the accuracy and suitability of the output for your specific purposes.

4. **Limited Support:** This software is a side project for MGS, and we cannot commit to providing ongoing support or maintenance. While we may provide assistance or updates at our discretion, you acknowledge that we are under no obligation to do so. You are encouraged to seek support from the open-source community or engage with MGS through public forums or channels if you encounter issues or have questions about the software.

5. **Creative Commons Attribution-NonCommercial-ShareAlike License:** The Software is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike (CC BY-NC-SA) license. By using the Software, User agrees to comply with the terms of this license. A copy of the CC BY-NC-SA license can be found in the accompanying LICENSE file or on the Creative Commons website.

6. **Indemnification:** You agree to indemnify, defend, and hold harmless MGS and its affiliates, officers, directors, employees, agents, licensors, and suppliers from and against any claims, liabilities, damages, losses, costs, or expenses, including reasonable attorneys' fees, arising out of or in connection with your use or misuse of the software, violation of these terms and conditions, or infringement of any third-party rights.

7. **Governing Law:** These terms and conditions shall be governed by and construed in accordance with the laws of the State of Michigan, without regard to its conflict of law principles. Any dispute arising out of or relating to these terms and conditions or your use of the software shall be exclusively resolved by the state or federal courts located in Michigan, and you consent to the personal jurisdiction and venue of such courts.

8. **Severability:** If any provision of these terms and conditions is held to be invalid, illegal, or unenforceable, the validity, legality, and enforceability of the remaining provisions shall not be affected or impaired in any way.

By using this code, you acknowledge that you have read, understood, and agree to be bound by these terms and conditions. If you do not agree to these terms and conditions, you are not authorized to use the software.
