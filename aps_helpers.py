import requests
import base64
import urllib.parse
from models.hubs import HubsList
from models.projects import ProjectsList
from models.folders import FoldersList
from models.contents import FolderContentsList


APS_BASE_URL = "https://developer.api.autodesk.com"

def get_hubs(token) -> HubsList:
    """
    Retrieves a list of hubs the user has access to.
    Corresponds to: GET /project/v1/hubs
    """
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{APS_BASE_URL}/project/v1/hubs", headers=headers)
    response.raise_for_status()
    # print(response.text)
    hubs_data = HubsList.model_validate_json(response.text)  # type: ignore[attr-defined]
    return hubs_data

def get_projects(hub_id, token) -> ProjectsList:
    """
    Retrieves a list of projects within a specific hub.
    Corresponds to: GET /project/v1/hubs/{hub_id}/projects
    """
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{APS_BASE_URL}/project/v1/hubs/{hub_id}/projects", headers=headers)
    response.raise_for_status()
    # print(response.text)
    return ProjectsList.model_validate_json(response.text)  # type: ignore[attr-defined]

def get_top_folders(hub_id, project_id, token) -> FoldersList:
    """
    Retrieves the top-level folders of a project.
    Corresponds to: GET /project/v1/hubs/{hub_id}/projects/{project_id}/topFolders
    """
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{APS_BASE_URL}/project/v1/hubs/{hub_id}/projects/{project_id}/topFolders", headers=headers)
    response.raise_for_status()
    # print("[DEBUG]", f"{response.text=}")
    return FoldersList.model_validate_json(response.text)  # type: ignore[attr-defined]


def get_folder_contents(project_id, folder_id, token) -> FolderContentsList:
    """
    Retrieves the contents (files and subfolders) of a specific folder.
    Corresponds to: GET /data/v1/projects/{project_id}/folders/{folder_id}/contents
    """
    headers = {"Authorization": f"Bearer {token}"}
    encoded_folder_id = urllib.parse.quote(folder_id) # URL-encode the ID
    url = f"https://developer.api.autodesk.com/data/v1/projects/{project_id}/folders/{encoded_folder_id}/contents"
    response = requests.get(url, headers=headers)
    # print("***")
    # print(response.text)
    response.raise_for_status()
    return FolderContentsList.model_validate_json(response.text)  # type: ignore[attr-defined]

def get_item_versions(project_id, item_id, token):
    """
    Retrieves all versions of a specific item (file).
    response.raise_for_status()

    Corresponds to: GET /data/v1/projects/{project_id}/items/{item_id}/versions
    """
    headers = {"Authorization": f"Bearer {token}"}
    encoded_item_id = urllib.parse.quote(item_id) # URL-encode the ID
    url = f"https://developer.api.autodesk.com/data/v1/projects/{project_id}/items/{encoded_item_id}/versions"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("data", [])

def get_model_views_and_metadata(urn, token):
    """
    Retrieves the model views (and their metadata) for a given file URN.
    The URN must be for a file that has been translated to SVF or SVF2.
    """
    encoded_urn = base64.urlsafe_b64encode(urn.encode()).decode().rstrip("=")
    headers = {"Authorization": f"Bearer {token}"}
    
    manifest_url = f"{APS_BASE_URL}/modelderivative/v2/designdata/{encoded_urn}/manifest"
    manifest_response = requests.get(manifest_url, headers=headers)
    
    # If the manifest doesn't exist (404), it means the file was never translated.
    if manifest_response.status_code == 404:
        print("    - Info: No derivative manifest found. File has not been translated.")
        return None
    
    # For any other error, raise it.
    manifest_response.raise_for_status()
    manifest = manifest_response.json()

    if manifest.get('status') != 'success':
        print(f"    - Translation status for {urn}: {manifest.get('status')} ({manifest.get('progress', '')})")
        return None

    metadata_url = f"{APS_BASE_URL}/modelderivative/v2/designdata/{encoded_urn}/metadata"
    metadata_response = requests.get(metadata_url, headers=headers)
    
    if metadata_response.status_code == 200:
        return metadata_response.json().get("data", {}).get("metadata", [])
    else:
        print(f"    - Could not retrieve metadata for {urn}. Status: {metadata_response.status_code}")
        return None

def get_hub_names(token):
    """Return a list of hub names for the given token."""
    hubs = get_hubs(token)
    if hubs and hasattr(hubs, "data"):
        return [hub.attributes.name for hub in hubs.data]
    return []


def get_hub_id_by_name(token, hub_name):
    """Return hub ID for a given hub name."""
    hubs = get_hubs(token)
    if hubs and hasattr(hubs, "data"):
        for hub in hubs.data:
            if getattr(hub.attributes, "name", None) == hub_name:
                return hub.id
    return None
def get_all_cad_file_from_hub(
    token: str,
    hub_id: str | None = None,
    *,
    include_views: bool = False,
) -> dict[str, dict[str, str]]:
    """
    Walk through the Autodesk APS hub structure and collect viewable CAD files.

    Returns a dict mapping display_name -> {"urn": <latest_version_urn>}
    Always returns a dict (possibly empty).
    """

    all_viewables: dict[str, dict[str, str]] = {}

    def process_hub(_hub_id: str) -> None:
        nonlocal all_viewables
        projects = get_projects(_hub_id, token)
        if projects and projects.data:
            for project in projects.data:
                project_name = project.attributes.name
                project_id_with_prefix = project.id  # already prefixed (e.g., "b.")
                # print(f"  Project: {project_name} (ID: {project_id_with_prefix})")

                top_folders = get_top_folders(_hub_id, project_id_with_prefix, token)
                if top_folders and top_folders.data:
                    for folder in top_folders.data:
                        viewables = get_all_cad_from_folder(
                            project_id_with_prefix,
                            folder.id,
                            token,
                            indent="    ",
                            include_views=include_views,
                        )
                        if viewables:
                            all_viewables.update(viewables)

    # If a specific hub_id is provided, process only that hub
    if hub_id:
        process_hub(hub_id)
        return all_viewables

    # Otherwise, enumerate all hubs available to this token
    hubs = get_hubs(token)
    if not hubs or not hubs.data:
        print("No hubs found for this token.")
        return {}

    for hub in hubs.data:
        hub_name = hub.attributes.name
        _hub_id = hub.id
        print(f"Hub: {hub_name} (ID: {_hub_id})")
        process_hub(_hub_id)

    return all_viewables


def get_all_cad_from_folder(project_id, folder_id, token, indent="", *, include_views: bool = False):
    """
    Recursively traverses a folder and its subfolders, printing contents.
    """
    viewable_files: dict[str, dict[str, str]] = {}
    try:
        contents = get_folder_contents(project_id, folder_id, token)
    except requests.exceptions.HTTPError as e:
        print(f"{indent}[Error accessing folder {folder_id}: {e}]")
        return viewable_files  # return an empty dict, not None

    if not contents.data:
        return viewable_files

    for content in contents.data:
        try:
            display_name = content.attributes.displayName
            content_type = content.type  # 'folders' or 'items'
            content_id = content.id

            # print(f"{indent}{content_type.capitalize()[:-1]}: {display_name}")

            if content_type == "folders":
                # Capture and merge the returned data
                sub_viewables = get_all_cad_from_folder(
                    project_id, content_id, token, indent + "  "
                )
                if sub_viewables:
                    viewable_files.update(sub_viewables)

            elif content_type == "items":
                supported_extensions = [
                    ".rvt",
                    ".dwg",
                    ".ifc",
                    ".step",
                    ".stp",
                    ".iam",
                    ".ipt",
                ]
                if any(
                    display_name.lower().endswith(ext) for ext in supported_extensions
                ):
                    versions = get_item_versions(
                        project_id, content_id, token
                    )
                    if versions:
                        latest_version = versions[0]
                        version_urn = latest_version["id"]
                        print(f"{indent}  - Latest Version URN: {version_urn}")
                        viewable_files[display_name] = {"urn": version_urn}
                        if include_views:
                            model_views = get_model_views_and_metadata(
                                version_urn, token
                            )
                            if model_views:
                                for view in model_views:
                                    print(
                                        f"{indent}    - View: {view.get('name')}, "
                                        f"GUID: {view.get('guid')}"
                                    )
                else:
                    print(f"{indent}  - (Skipping derivative check for non‑CAD file)")

        except (requests.exceptions.HTTPError, AttributeError) as item_error:
            display_name_for_error = "Unknown"
            if hasattr(content, "attributes") and hasattr(
                content.attributes, "displayName"
            ):
                display_name_for_error = content.attributes.displayName
            print(
                f"{indent}  [Could not process item {display_name_for_error}: {item_error}]"
            )
            continue

    return viewable_files