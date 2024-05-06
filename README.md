# Michigan Geological Survey: Cross-Section Tool Box
 The following tool was created to automate the process of creating project files for groundwater analysis, as well as provide a resource for establishing cross-sectional views of geologic data. The implementation of the tools is as follows:
1. Create an analysis-ready project with all necessary datasets within Michigan (Not applicable for other states).
2. Create analysis-ready water well datasets with complete data transformation and formatting to the standards set by the Michigan Geological Survey.
3. Generate groundwater surface profiles based on the needs of the project.
4. Generate full cross-section views of multiple lines utilizing:
   1. Borehole depths and lithologies.
   2. Screened intervals.
   3. Surface topography profiles.
   4. Bedrock topography profiles.
   5. Groundwater topography profiles.
   6. Gridded box profile.
5. Generate segments of the full cross-section tool as data is changed.

---

**IMPORTANT NOTES**

The processing time of all of the tools is directly related to the size of the project & size/number of cross-sections. Large scale projects with many cross-sections can take hours or even days to complete. This time will hopefully be reduced in the future through code optimizations and updates. 

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

**KNOWN ISSUES**

Both the Cross-Section (All Steps) and the (Borehole Sticks) tools take the longest on the "Segmenting Porfiles" portion but will sometimes freeze there. It may seem stuck during this phase but it can also just take a long time to move forward. Give it a half hour to 2 hours per cross-section line before cancelling and trying again.

---

**SPECIAL THANKS**

Special thank you to Evan Thoms and the rest of USGS for providing the base work that was used to create these tools.

---

**End-User License Agreement (EULA)**

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
