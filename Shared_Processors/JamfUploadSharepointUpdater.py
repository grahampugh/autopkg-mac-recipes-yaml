#!/usr/local/autopkg/python

"""
Copyright 2017 Graham Pugh

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import urllib

from shareplum import Site
from requests_ntlm2 import HttpNtlmAuth
from autopkglib import Processor, ProcessorError  # type: ignore

__all__ = ["JamfUploadSharepointUpdater"]


class JamfUploadSharepointUpdater(Processor):
    description = (
        "Performs actions on a SharePoint site based on output of a JSSImporter run."
    )
    input_variables = {
        "JSS_URL": {
            "required": True,
            "description": (
                "The JSS URL." "This can be set in the com.github.autopkg preferences"
            ),
        },
        "SP_URL": {
            "required": True,
            "description": (
                "The SharePoint URL."
                "This can be set in the com.github.autopkg preferences"
            ),
        },
        "SP_USER": {
            "required": True,
            "description": (
                "The SharePoint user that has access to the Sharepoint path."
                "This can be set in the com.github.autopkg preferences"
            ),
        },
        "SP_PASS": {
            "required": True,
            "description": (
                "The SharePoint user's password."
                "This can be set in the com.github.autopkg "
                "preferences"
            ),
        },
        "POLICY_CATEGORY": {
            "required": False,
            "description": ("Policy Category."),
            "default": "Untested",
        },
        "PKG_CATEGORY": {
            "required": True,
            "description": (
                "Package Category (which is ultimately the prod category)."
            ),
        },
        "LANGUAGE": {"required": False, "description": "Policy language."},
        "LICENSE": {"required": False, "description": "Package license type."},
        "MAJOR_VERSION": {"required": False, "description": "Policy major version."},
        "PLATFORM": {"required": False, "description": "Policy architecture."},
        "NAME": {"required": True, "description": "Product name."},
        "SELFSERVICE_POLICY_NAME": {
            "required": False,
            "description": ("Product production policy name."),
        },
        "version": {"required": True, "description": "Product version."},
    }
    output_variables = {}

    __doc__ = description

    def connect_sharepoint(self, url, user, password):
        """make a connection to SharePoint"""
        auth = HttpNtlmAuth(f"d\\{user}", password)
        site = Site(url, auth=auth)
        if not site:
            self.output(site, verbose_level=3)
            raise ProcessorError("Could not connect to SharePoint")
        return site

    def build_query(self, criteria):
        """construct the query. format should be
        {'Where': ['And', ('Eq', 'Title', 'Good Title'),
                          ('Eq', 'My Other Column', 'Nice Value')]}
        See https://shareplum.readthedocs.io/en/latest/queries.html
        """
        query = {"Where": []}
        fields = ["ID"]
        # If more than one value we want all to match, so use "and".
        # With shareplum, the last criteria should not have an "and".
        # To achieve this we build the query and then reverse it
        # (this only works because/when all criteria are "and").
        # See https://github.com/jasonrollins/shareplum/issues/17#issuecomment-342823183
        first = True
        for key in criteria:
            operand, value = criteria[key]
            query["Where"].append((operand, key, value))
            fields.append(key)
            if not first:
                query["Where"].append("And")
            if first:
                first = False
        query["Where"].reverse()
        self.output(query, verbose_level=3)
        return fields, query

    def check_list(self, site, listname, criteria):
        """Check an item is in a SharePoint list

        site            SharePoint site where the list is situated
        listname        name of of the list
        search_key      key to search against
        criteria        an dictionary of criteria (key/value) to search against
        """
        sp_list = site.List(listname)
        fields, query = self.build_query(criteria)

        if sp_list.GetListItems(fields=fields, query=query):
            return True

    def update_record(self, site, listname, list_key, list_value, criteria):
        """Update a value in a SharePoint list:

        site            SharePoint site where the list is situated
        listname        name of of the list
        list_key        key to update
        list_value      value to set in the key
        criteria        an dictionary of criteria (key/value) to search against
        """
        sp_list = site.List(listname)
        fields, query = self.build_query(criteria)

        for row in sp_list.GetListItems(fields=fields, query=query):
            update_data = []
            data = {"ID": row["ID"]}
            data[list_key] = list_value
            update_data.append(data)
            sp_list.UpdateListItems(data=update_data, kind="Update")

    def add_record(self, site, listname, list_key, list_value):
        """Update a value in a SharePoint list:

        site            SharePoint site where the list is situated
        listname        name of of the list
        list_key        key to update
        list_value      value to set in the key
        """
        sp_list = site.List(listname)
        new_record = {list_key: list_value}
        sp_list.UpdateListItems([new_record], "New")
        self.output(f"'{list_key}' added with value '{list_value}'")

    def delete_record(self, site, listname, criteria):
        """Delete an item from a SharePoint list

        site            SharePoint site where the list is situated
        listname        name of of the list
        criteria        an dictionary of criteria (key/value) to search against
        """
        sp_list = site.List(listname)
        fields, query = self.build_query(criteria)
        delete_data = []
        for row in sp_list.GetListItems(fields=fields, query=query):
            delete_data.append(row["ID"])
            sp_list.UpdateListItems(data=delete_data, kind="Delete")

    def test_report_url(self, sp_url, policy_name):
        """Creates the Test Report URL needed in Jamf Content List"""
        params = {"Title": policy_name}
        url_encoded = urllib.parse.urlencode(params)
        list_name_url = "Jamf_Item_Test"
        test_report_url = f"{sp_url}/Lists/{list_name_url}/DispForm.aspx?{url_encoded}"
        return test_report_url

    def main(self):
        """Do the main thing"""
        policy_category = self.env.get("POLICY_CATEGORY")
        category = self.env.get("PKG_CATEGORY")
        version = self.env.get("version")
        name = self.env.get("NAME")
        final_policy_name = self.env.get("SELFSERVICE_POLICY_NAME")
        policy_language = self.env.get("LANGUAGE")
        policy_license = self.env.get("LICENSE")
        major_version = self.env.get("MAJOR_VERSION")
        platform = self.env.get("PLATFORM")
        executable_command = self.env.get("SP_EXECUTABLE_COMMAND")
        process_name = self.env.get("SP_PROCESS_NAME")
        jss_url = self.env.get("JSS_URL")
        sp_url = self.env.get("SP_URL")
        sp_user = self.env.get("SP_USER")
        sp_pass = self.env.get("SP_PASS")

        # section for untested recipes (PRD server only)
        if not final_policy_name:
            if "prd" in jss_url:
                final_policy_name = name
                if major_version:
                    final_policy_name = final_policy_name + " " + major_version
                if policy_language:
                    final_policy_name = final_policy_name + " " + policy_language
                if policy_license:
                    final_policy_name = final_policy_name + " " + policy_license
                if platform:
                    final_policy_name = final_policy_name + " " + platform

                policy_name = f"{final_policy_name} (Testing)"
                self_service_policy_name = f"{final_policy_name} (Testing) v{version}"

                self.output(
                    "UNTESTED recipe type: "
                    "Sending updates to SharePoint based on Policy Name "
                    + final_policy_name
                )

                self.output("Name: %s" % name)
                self.output("Title: %s" % final_policy_name)
                self.output("Policy: %s" % policy_name)
                self.output("Version: %s" % version)
                self.output("SharePoint item: %s" % self_service_policy_name)
                self.output("Production Category: %s" % category)
                self.output("Current Category: %s" % policy_category)

                # connect to the sharepoint site
                site = self.connect_sharepoint(sp_url, sp_user, sp_pass)

                # Now write to the Jamf Content List
                # First, check if there is an existing entry for this policy
                criteria = {}
                criteria["Self Service Content"] = ["Eq", final_policy_name]

                app_in_content_list = self.check_list(
                    site, "Jamf Content List", criteria
                )

                # if not, create the entry
                if not app_in_content_list:
                    self.output(
                        "Jamf Content List: Adding new entry for " + final_policy_name
                    )
                    self.add_record(
                        site,
                        "Jamf Content List",
                        "Self Service Content",
                        final_policy_name,
                    )
                else:
                    self.output(
                        "Jamf Content List: Updating existing entry for "
                        + final_policy_name
                    )
                # now update the other keys in the entry
                self.output(
                    "Jamf Content List: Setting 'Untested Version' "
                    + version
                    + " for "
                    + final_policy_name
                )
                self.update_record(
                    site,
                    "Jamf Content List",
                    "Untested Version",
                    version,
                    criteria,
                )
                self.update_record(
                    site,
                    "Jamf Content List",
                    "Category",
                    category,
                    criteria,
                )
                self.update_record(
                    site,
                    "Jamf Content List",
                    "Content Type",
                    "Application",
                    criteria,
                )

                # Now write to Jamf Test Coordination list
                # First, check if the content is set to Autostage in the content list.
                criteria = {}
                criteria["Self Service Content"] = ["Eq", final_policy_name]
                criteria["Autostage"] = ["Eq", "Yes"]

                is_app_autostage = self.check_list(site, "Jamf Content List", criteria)
                if is_app_autostage:
                    self.output(
                        f"Jamf Content List: {final_policy_name} is set to Autostage"
                    )
                else:
                    self.output(
                        f"Jamf Content List: {final_policy_name} is not set to Autostage"
                    )

                # Now, check if there is an existing entry for this policy (including version)
                # which has been released
                criteria = {}
                criteria["Self Service Content Name"] = ["Eq", self_service_policy_name]
                criteria["Release Completed"] = ["Eq", "Yes"]

                exact_policy_in_test_coordination_and_released = self.check_list(
                    site, "Jamf Test Coordination", criteria
                )

                # if so, set back to release completed = No
                if exact_policy_in_test_coordination_and_released:
                    self.output(
                        "Jamf Test Coordination: Setting 'Release Completed'='No' for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Coordination",
                        "Release Completed",
                        "No",
                        criteria,
                    )
                # Now check if there is an existing entry for this policy (including version)
                # if so, existing tests are no longer valid, so ensure to set the entry
                # to 'Needs review' if some tests were already done
                criteria = {}
                criteria["Self Service Content Name"] = ["Eq", self_service_policy_name]

                exact_policy_in_test_coordination = self.check_list(
                    site, "Jamf Test Coordination", criteria
                )

                if exact_policy_in_test_coordination:
                    if is_app_autostage:
                        # set Status to Autostage on the existing entry
                        criteria = {}
                        criteria["Self Service Content Name"] = [
                            "Eq",
                            self_service_policy_name,
                        ]
                        criteria["Status"] = ["Neq", "Autostage"]

                        self.output(
                            "Jamf Test Coordination: Setting 'Status'='Autostage' for "
                            + self_service_policy_name
                        )
                        self.update_record(
                            site,
                            "Jamf Test Coordination",
                            "Status",
                            "Autostage",
                            criteria,
                        )
                    else:
                        # reset Status if any work had already been done on the existing entry
                        check_criteria = [
                            "In progress",
                            "Done",
                            "Deferred",
                            "Waiting for other test manager",
                        ]
                        for check in check_criteria:
                            criteria = {}
                            criteria["Self Service Content Name"] = [
                                "Eq",
                                self_service_policy_name,
                            ]
                            criteria["Release Completed"] = ["Eq", "No"]
                            criteria["Status"] = ["Eq", check]
                            app_in_test_coordination_tested_but_not_released = (
                                self.check_list(
                                    site, "Jamf Test Coordination", criteria
                                )
                            )
                            if app_in_test_coordination_tested_but_not_released:
                                self.output(
                                    "Jamf Test Coordination: Setting 'Status'='Needs review' for "
                                    + self_service_policy_name
                                )
                                self.update_record(
                                    site,
                                    "Jamf Test Coordination",
                                    "Status",
                                    "Needs review",
                                    criteria,
                                )
                else:
                    # check if there is an entry with the same final policy name that is
                    # not release completed
                    criteria = {}
                    criteria["Final Content Name"] = ["Eq", final_policy_name]
                    criteria["Release Completed"] = ["Eq", "No"]
                    criteria["Status"] = ["Neq", "Obsolete"]

                    app_in_test_coordination_not_released = self.check_list(
                        site,
                        "Jamf Test Coordination",
                        criteria,
                    )
                    if app_in_test_coordination_not_released:
                        self.output(
                            "Jamf Test Coordination: Updating existing unreleased "
                            "entry for " + final_policy_name
                        )
                        self.output(
                            "Jamf Test Coordination: Setting 'Status'='Obsolete' for "
                            + final_policy_name
                        )
                        self.update_record(
                            site,
                            "Jamf Test Coordination",
                            "Status",
                            "Obsolete",
                            criteria,
                        )

                    # now create a new entry
                    self.output(
                        "Jamf Test Coordination: Adding record for "
                        + self_service_policy_name
                    )
                    self.add_record(
                        site,
                        "Jamf Test Coordination",
                        "Self Service Content Name",
                        self_service_policy_name,
                    )

                    criteria = {}
                    criteria["Self Service Content Name"] = [
                        "Eq",
                        self_service_policy_name,
                    ]

                    self.output(
                        "Jamf Test Coordination: Setting 'Final Content Name' "
                        + final_policy_name
                        + " for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Coordination",
                        "Final Content Name",
                        final_policy_name,
                        criteria,
                    )
                    if is_app_autostage:
                        self.output(
                            "Jamf Test Coordination: Setting 'Status'='Autostage' for "
                            + self_service_policy_name
                        )
                        self.update_record(
                            site,
                            "Jamf Test Coordination",
                            "Status",
                            "Autostage",
                            criteria,
                        )

                # Now write to Jamf Test Review list
                # First, check if there is an existing entry for this policy (including version)
                criteria = {}
                criteria["Self Service Content Name"] = ["Eq", self_service_policy_name]

                exact_policy_in_test_review = self.check_list(
                    site, "Jamf Test Review", criteria
                )

                # if so, existing tests are no longer valid, so set the entry to
                # Release Completed='False' and Ready for Production="No"
                if exact_policy_in_test_review:
                    self.output(
                        "Jamf Test Review: Updating existing entry for "
                        + self_service_policy_name
                    )
                    self.output(
                        "Jamf Test Review: Setting 'Release Completed TST'='No' for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Review",
                        "Release Completed TST",
                        "No",
                        criteria,
                    )
                    self.output(
                        "Jamf Test Review: Setting 'Release Completed PRD'='No' for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Review",
                        "Release Completed PRD",
                        "No",
                        criteria,
                    )
                    self.output(
                        "Jamf Test Review: Setting 'Ready for Production'='No' for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Review",
                        "Ready for Production",
                        "No",
                        criteria,
                    )
                    self.output(
                        "Jamf Test Review: Setting 'ApplicationName'='applicaton_name' for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Review",
                        "Executable_Command",
                        executable_command,
                        criteria,
                    )
                    self.output(
                        "Jamf Test Review: Setting 'Process_Name'='process_name' for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Review",
                        "Process_Name",
                        process_name,
                        criteria,
                    )
                else:
                    # check if there is an entry with the same final policy name that is not
                    # release completed in TST or PRD
                    criteria = {}
                    criteria["Final Content Name"] = ["Eq", final_policy_name]
                    criteria["Release Completed TST"] = ["Eq", "No"]

                    app_in_test_review_not_released = self.check_list(
                        site,
                        "Jamf Test Review",
                        criteria,
                    )

                    # if not release completed in TST, delete the record
                    if app_in_test_review_not_released:
                        self.output(
                            "Jamf Test Review: Deleting existing unreleased entry for "
                            + final_policy_name
                        )
                        self.delete_record(
                            site,
                            "Jamf Test Review",
                            criteria,
                        )
                    # if not release completed in PRD, set the record to skipped
                    else:
                        criteria = {}
                        criteria["Final Content Name"] = ["Eq", final_policy_name]
                        criteria["Release Completed PRD"] = ["Eq", "No"]

                        app_in_test_review_not_released_to_prd = self.check_list(
                            site,
                            "Jamf Test Review",
                            criteria,
                        )
                        if app_in_test_review_not_released_to_prd:
                            self.output(
                                "Jamf Test Review: Setting existing unreleased (PRD) entry "
                                f"for '{final_policy_name}' to 'Skipped'"
                            )
                            self.update_record(
                                site,
                                "Jamf Test Review",
                                "Release Completed PRD",
                                "Skipped",
                                criteria,
                            )

                    # now create a new entry
                    self.output(
                        "Jamf Test Review: Adding record for" + self_service_policy_name
                    )
                    self.add_record(
                        site,
                        "Jamf Test Review",
                        "Self Service Content Name",
                        self_service_policy_name,
                    )
                    criteria = {}
                    criteria["Self Service Content Name"] = [
                        "Eq",
                        self_service_policy_name,
                    ]
                    self.output(
                        "Jamf Test Review: Setting 'Final Content Name' "
                        + final_policy_name
                        + " for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Review",
                        "Final Content Name",
                        final_policy_name,
                        criteria,
                    )
                    self.output(
                        "Jamf Test Review: Setting 'Executable_Command'='executable_command' for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Review",
                        "Executable_Command",
                        executable_command,
                        criteria,
                    )
                    self.output(
                        "Jamf Test Review: Setting 'Process_Name'='process_name' for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Review",
                        "Process_Name",
                        process_name,
                        criteria,
                    )

        # section for prod recipes
        else:
            self_service_policy_name = f"{final_policy_name} (Testing) v{version}"

            self.output("Name: " + name)
            self.output("Policy: " + final_policy_name)
            self.output("Version: " + version)
            self.output("SharePoint item: " + self_service_policy_name)
            self.output("Production Category: " + category)
            self.output("Current Category: " + policy_category)

            self.output("PROD recipe type: Sending staging instructions to SharePoint")
            # connect to the sharepoint site
            site = self.connect_sharepoint(sp_url, sp_user, sp_pass)

            # Now write to Jamf Test Coordination list
            # Here we need to set Release Completed to True

            # First, check if there is an existing entry for this policy (including version)
            criteria = {}
            criteria["Self Service Content Name"] = ["Eq", self_service_policy_name]

            exact_policy_in_test_coordination = self.check_list(
                site, "Jamf Test Coordination", criteria
            )

            # if not, we should create one
            if exact_policy_in_test_coordination:
                self.output(
                    "Jamf Test Coordination: Updating existing entry for "
                    + self_service_policy_name
                )
            else:
                self.output(
                    "Jamf Test Coordination: Adding record for "
                    + self_service_policy_name
                )
                self.add_record(
                    site,
                    "Jamf Test Coordination",
                    "Self Service Content Name",
                    self_service_policy_name,
                )
                self.output(
                    "Jamf Test Coordination: Setting 'Final Content Name' "
                    + final_policy_name
                    + " for "
                    + self_service_policy_name
                )
                self.update_record(
                    site,
                    "Jamf Test Coordination",
                    "Final Content Name",
                    final_policy_name,
                    criteria,
                )

            # set Jamf Test Coordination to "Release Completed"="Yes" only from PRD
            if "prd" in jss_url:
                # First, check if the content is set to Autostage in the content list.
                autostage_criteria = {}
                autostage_criteria["Self Service Content"] = ["Eq", final_policy_name]
                autostage_criteria["Autostage"] = ["Eq", "Yes"]

                is_app_autostage = self.check_list(
                    site, "Jamf Content List", autostage_criteria
                )
                if is_app_autostage:
                    self.output(
                        f"Jamf Content List: {final_policy_name} is set to Autostage"
                    )
                else:
                    self.output(
                        f"Jamf Content List: {final_policy_name} is not set to Autostage"
                    )
                # now write the changes to Test Coordination
                self.output(
                    "Jamf Test Coordination: Setting 'Release Completed'='Yes' for "
                    + self_service_policy_name
                )
                self.update_record(
                    site,
                    "Jamf Test Coordination",
                    "Release Completed",
                    "Yes",
                    criteria,
                )
                if is_app_autostage:
                    self.output(
                        "Jamf Test Coordination: Setting 'Status'='Autostage' for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Coordination",
                        "Status",
                        "Autostage",
                        criteria,
                    )
                else:
                    self.output(
                        "Jamf Test Coordination: Setting 'Status'='Done' for "
                        + self_service_policy_name
                    )
                    self.update_record(
                        site,
                        "Jamf Test Coordination",
                        "Status",
                        "Done",
                        criteria,
                    )

            # Now write to Jamf Test Review list
            # Here we need to set Release Completed to True
            # First, check if there is an existing entry for this policy (including version)
            criteria = {}
            criteria["Self Service Content Name"] = ["Eq", self_service_policy_name]
            exact_policy_in_test_review = self.check_list(
                site, "Jamf Test Review", criteria
            )

            # if not, we should create one
            if exact_policy_in_test_review:
                self.output(
                    "Jamf Test Review: Updating existing entry for "
                    + self_service_policy_name
                )
            else:
                self.output(
                    "Jamf Test Review: Adding record for " + self_service_policy_name
                )
                self.add_record(
                    site,
                    "Jamf Test Review",
                    "Self Service Content Name",
                    self_service_policy_name,
                )
                self.output(
                    "Jamf Test Review: Setting 'Final Content Name' "
                    + final_policy_name
                    + " for "
                    + self_service_policy_name
                )
                self.update_record(
                    site,
                    "Jamf Test Review",
                    "Final Content Name",
                    final_policy_name,
                    criteria,
                )
            # set Jamf Test Review to "Release Completed" only from TST
            if "tst" in jss_url:
                self.output(
                    "Jamf Test Review: Setting 'Release Completed TST'='Yes' for "
                    + self_service_policy_name
                )
                self.update_record(
                    site,
                    "Jamf Test Review",
                    "Release Completed TST",
                    "Yes",
                    criteria,
                )
                # Set ready for production to Yes in case we are forcing the staging
                self.output(
                    "Jamf Test Review: Setting 'Ready for Production'='Yes' for "
                    + self_service_policy_name
                )
                self.update_record(
                    site,
                    "Jamf Test Review",
                    "Ready for Production",
                    "Yes",
                    criteria,
                )
            # set Jamf Test Review to "Release Completed PRD"="Yes" only from PRD
            elif "prd" in jss_url:
                self.output(
                    "Jamf Test Review: Setting 'Release Completed PRD'='Yes' for "
                    + self_service_policy_name
                )
                self.update_record(
                    site,
                    "Jamf Test Review",
                    "Release Completed PRD",
                    "Yes",
                    criteria,
                )

            # Now write to the Jamf Content List (PRD only)
            # Here we need to clear the untested version, change the prod version, and
            # add the test report URL
            # First, check if there is an existing entry for this policy
            if "prd" in jss_url:
                criteria = {}
                criteria["Self Service Content"] = ["Eq", final_policy_name]
                app_in_content_list = self.check_list(
                    site, "Jamf Content List", criteria
                )

                # if not, create the entry
                if not app_in_content_list:
                    self.output(
                        "Jamf Content List: Adding new entry for " + final_policy_name
                    )
                    self.add_record(
                        site,
                        "Jamf Content List",
                        "Self Service Content",
                        final_policy_name,
                    )
                else:
                    self.output(
                        "Jamf Content List: Updating existing entry for "
                        + final_policy_name
                    )
                # now update the other keys in the entry
                self.output(
                    "Jamf Content List: Clearing 'Untested Version' for "
                    + final_policy_name
                )
                self.update_record(
                    site,
                    "Jamf Content List",
                    "Untested Version",
                    "",
                    criteria,
                )
                self.output(
                    "Jamf Content List: Setting 'Prod. Version'='"
                    + version
                    + "' for "
                    + final_policy_name
                )
                self.update_record(
                    site, "Jamf Content List", "Prod. Version", version, criteria
                )
                # Test Report requires special work as it is a dictionary of title and url
                self.output(
                    "Jamf Content List: Setting 'Test Report' for " + final_policy_name
                )
                self.update_record(
                    site,
                    "Jamf Content List",
                    "Test Report",
                    self.test_report_url(sp_url, self_service_policy_name)
                    + ", Test Report",
                    criteria,
                )


if __name__ == "__main__":
    PROCESSOR = JamfUploadSharepointUpdater()
    PROCESSOR.execute_shell()
