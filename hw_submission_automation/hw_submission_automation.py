#!/usr/bin/env python3

"""
Examples:
  python3 hw_submission_automation.py -n test_rng -g 11.latest -p /home/271_RNG_win11_unsigned.hlkx -d 2025-06-24
  python3 hw_submission_automation.py submit -n test_rng -g 11.latest -p /home/271_RNG_win11_unsigned.hlkx -d 2025-06-24
"""

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
import itertools
from datetime import datetime
from pathlib import Path
from typing import List, Optional


def slugify(value, allow_unicode=False):
    """
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, dot, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s\.-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


class SDCMWrapper:
    """Python wrapper that generate RH-specific JSON and run SDCM"""

    def __init__(self, sdcm_path: str = None):
        # Save the executable file path or name specified by the user
        if sdcm_path is None:
            # OS-specific default executable name
            if sys.platform.startswith("win"):
                self.sdcm_executable = "SurfaceDevCenterManager.exe"
            else:
                self.sdcm_executable = "SurfaceDevCenterManager"
        else:
            self.sdcm_executable = sdcm_path

        # Verify that the SDCM executable file exists
        self._verify_sdcm()

    def _verify_sdcm(self):
        # Verify the SDCM and its configuration files exist and is executable
        if os.path.isabs(self.sdcm_executable):
            executable_path = self.sdcm_executable
        else:
            # Search for executable file
            executable_path = self._find_executable(self.sdcm_executable)

            if not executable_path:
                raise FileNotFoundError(f"SDCM executable '{self.sdcm_executable}' not found in system PATH")

        # Verify that the file exists
        if not os.path.isfile(executable_path):
            raise FileNotFoundError(f"SDCM not found at {executable_path}")

        # Verify executable permissions
        if not os.access(executable_path, os.X_OK):
            raise PermissionError(f"SDCM is not executable at {executable_path}")

        # Check the configuration file (in the same directory as the binary file
        sdcm_dir = os.path.dirname(executable_path)
        config_path = os.path.join(sdcm_dir, "authconfig.json")

        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"Required config file 'authconfig.json' not found in {sdcm_dir}")
        # Execute basic command verification function
        try:
            result = subprocess.run(
                [executable_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            # Check if the return code is 0 (SUCCESS)
            if result.returncode != 0:
                raise RuntimeError(f"SDCM execution failed (code={result.returncode}): {result.stdout} {result.stderr}")
        except subprocess.TimeoutExpired:
            pass

        # Save the full executable file path
        self.sdcm_path = executable_path

    def _find_executable(self, executable_name: str) -> str:
        """Find the executable file in the current directory, script directory, or system PATH"""
        # Check if the executable is in the script directory
        script_dir = Path(__file__).parent / executable_name
        if script_dir.is_file():
            return str(script_dir)

        # Check if the executable is in the current executable directory
        executable_dir = Path(sys.executable).parent / executable_name
        if executable_dir.is_file():
            return str(executable_dir)

        # Check if the executable is in the current directory
        current_dir = Path.cwd() / executable_name
        if current_dir.is_file():
            return str(current_dir)

        # If not found, search in the system PATH
        return self._find_executable_in_path(executable_name)

    def _find_executable_in_path(self, executable_name: str) -> str:
        """Find the executable file in the system PATH"""
        path_dirs = os.getenv("PATH", "").split(os.pathsep)

        for dir_path in path_dirs:
            candidate = Path(dir_path) / executable_name
            if candidate.is_file():
                return str(candidate)

        return None

    def _run_sdcm(self, args: List[str]) -> str:
        """Execute SDCM command and return output"""
        command = [self.sdcm_path] + args

        try:
            result = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            output = result.stdout.strip()
            error = result.stderr.strip()
            if output:
                print(f"SDCM output:\n{output}")
            if error:
                print(f"SDCM warnings/errors:\n{error}")
            return output
        except subprocess.CalledProcessError as e:
            error_msg = (
                f"SDCM command failed with code {e.returncode}:\n"
                f"Command: {' '.join(command)}\n"
                f"Stdout output: {e.output.strip()}\n"
                f"Stderr output: {e.stderr.strip()}"
            )
            raise RuntimeError(error_msg) from e

    def create_product(
        self,
        product_name: str,
        test_harness: str,
        announcement_date: str,
        marketing_names: List[str],
        selected_product_types: List[str],
        requested_signatures: List[str],
        output_file: str = None,
        **kwargs,
    ) -> str:
        """
        Create a product with configurable selectedProductTypes
        product_name: The name of the driver as
                      specified during creation
        test_harness: The type of package submitted
                      "HLK" or "Attestation"
        announcement_date: GA date
        marketing_names: List of marketing names of the product
        selected_product_types: List of type of the product
        requested_signatures: List of operating system signatures
                              for which product is certified
        output_file: Optional output JSON file path
        kwargs: Additional product attributes
        Returns:
            Product ID (PID)
        """
        config = {
            "createType": "product",
            "createProduct": {
                "productName": product_name,
                "testHarness": test_harness,
                "announcementDate": announcement_date,
                "deviceMetadataIds": None,
                "firmwareVersion": "0",
                "deviceType": "internalExternal",
                "isTestSign": False,
                "isFlightSign": False,
                "marketingNames": marketing_names,
                "selectedProductTypes": {},
                "requestedSignatures": requested_signatures,
                "additionalAttributes": None,
            },
        }
        # Set all selectedProductTypes
        for product_type in selected_product_types:
            config["createProduct"]["selectedProductTypes"][product_type] = "Unclassified"

        output_file = output_file or slugify(f"Create_Product_{product_name}.json")
        with open(output_file, "w") as f:
            json.dump(config, f, indent=4)
        output = self._run_sdcm(["--create", output_file])

        # Simple parsing to find product ID from output, might need adjustment depending on output format
        match = re.search(r"---- Product:\s*(\d+)", output)
        if match:
            pid = match.group(1)
            return pid
        return None

    def create_submission(
        self,
        product_id: str,
        submission_name: str,
        submission_type: str = "initial",
        output_file: str = None,
    ) -> str:
        """
        Create a submission
        product_id: PID from product creation
        submission_name: The name of the submission
        submission_type: "initial" or "derived"
        output_file: Optional output JSON file path
        Returns:
            Submission ID (SID)
        """
        config = {
            "createType": "submission",
            "createSubmission": {"name": submission_name, "type": submission_type},
        }
        output_file = output_file or slugify(f"Create_Submission_{submission_name}.json")
        with open(output_file, "w") as f:
            json.dump(config, f, indent=4)
        output = self._run_sdcm(["--create", output_file, "--productid", product_id])

        match = re.search(r"---- Submission:\s*(\d+)", output)
        if match:
            sid = match.group(1)
            return sid
        return None

    # Other operations (upload, commit, wait, download, list)
    def upload_package(self, package_path: str, product_id: str, submission_id: str) -> str:
        """Upload package to submission"""
        # if not os.path.exists(package_path):
        # raise FileNotFoundError(f"Package file not found: {package_path}")
        return self._run_sdcm(
            [
                "--upload",
                package_path,
                "--productid",
                product_id,
                "--submissionid",
                submission_id,
            ]
        )

    def commit_submission(self, product_id: str, submission_id: str) -> str:
        """Commit submission"""
        return self._run_sdcm(["--commit", "--productid", product_id, "--submissionid", submission_id])

    def wait_for_submission(self, product_id: str, submission_id: str) -> str:
        """Wait for submission completion"""
        return self._run_sdcm(["--wait", "--productid", product_id, "--submissionid", submission_id])

    def download_results(self, product_id: str, submission_id: str, output_file: str) -> str:
        """Download submission results"""
        return self._run_sdcm(
            [
                "--download",
                output_file,
                "--productid",
                product_id,
                "--submissionid",
                submission_id,
            ]
        )

    def download_metadata(self, product_id: str, submission_id: str, output_file: str) -> str:
        """Download submission metadata"""
        return self._run_sdcm(
            [
                "--metadata",
                output_file,
                "--productid",
                product_id,
                "--submissionid",
                submission_id,
            ]
        )

    def list_products(self) -> str:
        """List all products"""
        return self._run_sdcm(["--list", "product"])

    def list_submissions(self, product_id: str, submission_id: Optional[str] = None) -> str:
        """List submissions for a product"""
        cmd = ["--list", "submission", "--productid", product_id]
        if submission_id:
            cmd.extend(["--submissionid", submission_id])
        return self._run_sdcm(cmd)


def format_date_to_iso(date_str):
    # The basic format of ISO 8601 is: `YYYY - MM - DDTHH:mm:ss.sss

    return datetime.strptime(date_str, "%Y-%m-%d").isoformat()


def parse_arguments():
    """Parse command line arguments using argparse"""
    parser = argparse.ArgumentParser(
        description="Hardware submission automation tool for SDCM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "-t", "--test_harness",
        default="HLK",
        help="parse test_harness, valid value: HLK(default),Attestation"
    )
    parser.add_argument(
        "-n", "--product_name",
        help="parse product name, eg: 'Red Hat VirtIO RNG Drivers for Windows 11'"
    )
    parser.add_argument(
        "-a", "--guest_arch",
        default="x64",
        help="parse specified guest architecture. Valid value: x86,x64(default),mixed,ARM64"
    )
    parser.add_argument(
        "-g", "--guest_names",
        help="""
        parse specified guest platform.
        Valid value:
         x86: 10_1511, 10_1607, 10_1703, 10_1709, 10_1803, 10_1809, 10_19H1, 10_2004, 10.all, 10.latest
         x64: 10_1511, 10_1607, 10_1703, 10_1709, 10_1803, 10_1809, 10_19H1, 10_2004, 10_21H2, 11_22H2, 11_24H2, 16, 19, 22,
            25, 10.all, 11.all, 10.latest, 11.latest
         ARM64: 10_1709, 10_1803, 10_19H1, 10_2004, 10_21H2, 11_22H2, 11_24H2, 22, 25, 10.all, 11.all, 10.latest, 11.latest
         Examples:
          11.latest
          10_1803,10_2004
          10.all"""
    )
    parser.add_argument(
        "-s", "--submission_name",
        help="parse submission name, default value is the same with product_name"
    )
    parser.add_argument(
        "-p", "--package_path",
        help="parse package file path eg: /home/271_RNG_win11_unsigned.hlkx"
    )
    parser.add_argument(
        "-d", "--announcement_date",
        default="2025-01-01",
        help="Parse announcement date (GA) in YYYY-MM-DD format (e.g., 2025-06-24)"
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="submit",
        choices=["submit", "wait_download"],
        help="Action to perform: submit (default) or wait_download"
    )

    parser.add_argument(
        "-pid", "--product_id",
        help="Parse product ID"
    )

    parser.add_argument(
        "-sid", "--submission_id",
        help="Parse submission ID"
    )

    parser.add_argument(
        "-o", "--output_file",
        help="Parse output file path (e.g., /path/to/file.signed.zip)"
    )
    return parser.parse_args()


def gen_guest_mapping():
    # https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/get-product-data#list-of-operating-system-codes
    mapping = {
        "x86": {
            "10_1511": [("WINDOWS_v100_TH2_FULL", "Windows_v100")],
            "10_1607": [("WINDOWS_v100_RS1_FULL", "Windows_v100_RS1")],
            "10_1703": [("WINDOWS_v100_RS2_FULL", "Windows_v100_RS2")],
            "10_1709": [("WINDOWS_v100_RS3_FULL", "Windows_v100_RS3")],
            "10_1803": [("WINDOWS_v100_RS4_FULL", "Windows_v100_RS4")],
            "10_1809": [("WINDOWS_v100_RS5_FULL", "Windows_v100_RS5")],
            "10_19H1": [("WINDOWS_v100_19H1_FULL", "Windows_v100_19H1")],
            "10_2004": [("WINDOWS_v100_VB_FULL", "Windows_v100_VB")],
        },
        "x64": {
            "10_1511": [("WINDOWS_v100_X64_TH2_FULL", "Windows_v100")],
            "10_1607": [("WINDOWS_v100_X64_RS1_FULL", "Windows_v100_RS1")],
            "10_1703": [("WINDOWS_v100_X64_RS2_FULL", "Windows_v100_RS2")],
            "10_1709": [("WINDOWS_v100_X64_RS3_FULL", "Windows_v100_RS3")],
            "10_1803": [("WINDOWS_v100_X64_RS4_FULL", "Windows_v100_RS4")],
            "10_1809": [("WINDOWS_v100_X64_RS5_FULL", "Windows_v100_RS5")],
            "10_19H1": [("WINDOWS_v100_X64_19H1_FULL", "Windows_v100_19H1")],
            "10_2004": [("WINDOWS_v100_X64_VB_FULL", "Windows_v100_VB")],
            "10_21H2": [("WINDOWS_v100_X64_CO_FULL", "Windows_v100_CO")],
            "11_22H2": [("WINDOWS_v100_X64_NI_FULL", "Windows_v100_NI")],
            "11_24H2": [("WINDOWS_v100_X64_GE_FULL", "Windows_v100_GE")],
            "16": [("WINDOWS_v100_SERVER_X64_RS1_FULL", "Windows_v100Server_RS1")],
            "19": [("WINDOWS_v100_SERVER_X64_RS5_FULL", "Windows_v100Server_RS5")],
            "22": [("WINDOWS_v100_SERVER_X64_FE_FULL", "Windows_v100Server_FE")],
            "25": [("WINDOWS_v100_SERVER_X64_GE_FULL", "Windows_v100Server_GE")],
        },
        "ARM64": {
            "10_1709": [("WINDOWS_v100_ARM64_RS3_FULL", "Windows_v100_RS3")],
            "10_1803": [("WINDOWS_v100_ARM64_RS4_FULL", "Windows_v100_RS4")],
            # '10_1809':  [ ('WINDOWS_v100_X64_RS5_FULL', 'Windows_v100_RS5') ]  , Windows 10 Client version 1809 Client ARM64 [ (RS5) ]
            "10_19H1": [("WINDOWS_v100_ARM64_19H1_FULL", "Windows_v100_19H1")],
            "10_2004": [("WINDOWS_v100_ARM64_VB_FULL", "Windows_v100_VB")],
            "10_21H2": [("WINDOWS_v100_ARM64_CO_FULL", "Windows_v100_CO")],
            "11_22H2": [("WINDOWS_v100_ARM64_NI_FULL", "Windows_v100_NI")],
            "11_24H2": [("WINDOWS_v100_ARM64_GE_FULL", "Windows_v100_GE")],
            "22": [("WINDOWS_v100_SERVER_ARM64_FE_FULL", "Windows_v100Server_FE")],
            "25": [("WINDOWS_v100_SERVER_ARM64_GE_FULL", "Windows_v100Server_GE")],
        },
    }

    # TODO: Special cases for QE and Build system usage
    # Add the "10" option for x86, x64 and ARM64 with combined signatures of Windows 10 versions
    for arch in ["x86", "x64", "ARM64"]:
        mapping[arch]["10.all"] = []
        for key in mapping[arch].keys():
            if re.match('^10_.*', key):
                #print(f"Adding {mapping[arch][key]} to {arch} 10")
                mapping[arch]["10.all"].append(mapping[arch][key])
        mapping[arch]["10.all"] = list(itertools.chain.from_iterable(mapping[arch]["10.all"]))

    # Add the "11" option for x64 and ARM64 with combined signatures of Windows 11 versions
    for arch in ["x64", "ARM64"]:
        mapping[arch]["11.all"] = []
        for key in mapping[arch].keys():
            if re.match('^11_.*', key):
                #print(f"Adding {mapping[arch][key]} to {arch} 11")
                mapping[arch]["11.all"].append(mapping[arch][key])
        mapping[arch]["11.all"] = list(itertools.chain.from_iterable(mapping[arch]["11.all"]))

    # Add the options "10.latest/11.latest" for all architectures
    mapping["x86"]["10.latest"] = mapping["x86"]["10_2004"]
    mapping["x64"]["10.latest"] = mapping["x64"]["10_21H2"]
    mapping["ARM64"]["10.latest"] = mapping["ARM64"]["10_21H2"]

    mapping["x64"]["11.latest"] = mapping["x64"]["11_24H2"]
    mapping["ARM64"]["11.latest"] = mapping["ARM64"]["11_24H2"]

    return mapping


def main_submit(args):
    # Validate required arguments for submit action
    if not args.product_name:
        print("Error: --product_name is required for submit action")
        sys.exit(1)
    if not args.guest_names:
        print("Error: --guest_names is required for submit action")
        sys.exit(1)
    if not args.package_path:
        print("Error: --package_path is required for submit action")
        sys.exit(1)

    marketing_names = []

    guest_mapping = gen_guest_mapping()

    print("Dump guest mapping:")
    for arch, guests in guest_mapping.items():
        print(f"  {arch}: {guests.keys()}")

    requested_signatures = []
    selected_product_types = []

    for guest_name in args.guest_names.split(","):
        if args.guest_arch == "mixed":
            arch_list = ["x86", "x64"]
        else:
            arch_list = [args.guest_arch]
        for arch in arch_list:
            current_mappings = guest_mapping[arch][guest_name]
            for mapping in current_mappings:
                requested_signatures.append(mapping[0])
                selected_product_types.append(mapping[1])

    requested_signatures = list(set(requested_signatures))
    selected_product_types = list(set(selected_product_types))

    submission_name = args.submission_name
    if not submission_name:
        print(f"Submission name is not specified, using product name: {args.product_name}")
        submission_name = args.product_name

    marketing_names = [args.product_name]

    if args.test_harness == "Attestation":
        marketing_names = []
        selected_product_types = []
        print("Attestation test harness selected, no marketing names or product types will be set.")

    # we always keep these three value the same when submit manually.
    announcement_date = format_date_to_iso(args.announcement_date)

    print("SDCM product creation parameters:")
    print(f" Test harness: {args.test_harness}")
    print(f" Product name: {args.product_name}")
    print(f" Guest names: {args.guest_names}")
    print(f" Guest architecture: {args.guest_arch}")
    print(f"   - Requested signatures: {requested_signatures}")
    print(f"   - Selected product types: {selected_product_types}")
    print(f" Package path: {args.package_path}")
    print(f" Announcement date: {announcement_date}")
    print(f" Submission name: {submission_name}")
    print(f" Marketing names: {marketing_names}")

    wrapper = SDCMWrapper()
    pid = wrapper.create_product(
        args.product_name,
        args.test_harness,
        announcement_date,
        marketing_names,
        selected_product_types,
        requested_signatures,
    )
    if not pid:
        print(f"Failed to create product: {args.product_name}")
        sys.exit(1)

    sid = wrapper.create_submission(pid, submission_name)
    if not sid:
        print(f"Failed to create submission: {submission_name}")
        sys.exit(1)

    wrapper.upload_package(args.package_path, pid, sid)
    wrapper.commit_submission(pid, sid)

    create_results = {
        "product_id": pid,
        "submission_id": sid,
        "product_name": args.product_name,
        "submission_name": submission_name,
    }
    create_results_file = slugify(f"Result_Product_{args.product_name}.json")
    with open(create_results_file, "w") as f:
        json.dump(create_results, f, indent=4)


def main_wait_download(args):
    print(f"[INFO] Download action selected")

    if not args.product_id:
        print("Error: --product_id is required for download action")
        sys.exit(1)
    if not args.submission_id:
        print("Error: --submission_id is required for download action")
        sys.exit(1)
    if not args.output_file:
        print("Error: --output_file is required for download action")
        sys.exit(1)

    output_file = os.path.abspath(args.output_file)

    wrapper = SDCMWrapper()
    print(f"Waiting for submission with product ID: {args.product_id} and submission ID: {args.submission_id}")
    results = wrapper.wait_for_submission(args.product_id, args.submission_id)
    print(f"Submission completed")

    wrapper.download_results(args.product_id, args.submission_id, output_file)
    print(f"Results downloaded to: {output_file}")

    if "> driverMetadata Url" in results:
        print(f"Driver metadata URL found in submission results")
        metadata_file = output_file + "_metadata.json"
        wrapper.download_metadata(args.product_id, args.submission_id, metadata_file)


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()

    # Check that action is supported
    if args.action not in ["submit", "wait_download"]:
        print(f"Error: Unsupported action '{args.action}'")
        print("Supported actions: submit, wait_download")
        sys.exit(1)

    # Call appropriate main function based on action
    if args.action == "submit":
        main_submit(args)
    elif args.action == "wait_download":
        main_wait_download(args)
