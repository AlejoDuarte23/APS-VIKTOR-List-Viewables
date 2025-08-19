from pathlib import Path
import requests
import base64
import viktor as vkt  # type: ignore
import aps_helpers


class APSView(vkt.WebView):
    pass


def get_view_options(params, **kwargs):
    """
    Fetch the list of 3D and 2D views by parsing the derivative manifest 
    and returning OptionListElements with the correct "view" GUID.
    """
    if not params.viewable_file:
        return ["Select a viewable file first"]
        
    viewable_dict = get_viewable_files_dict(params, **kwargs)
    urn = viewable_dict.get(params.viewable_file, {}).get("urn")
    if not urn:
        return ["Could not find URN for the selected file"]

    integration = vkt.external.OAuth2Integration("aps-integration-1")
    token = integration.get_access_token()
    
    encoded_urn = base64.urlsafe_b64encode(urn.encode()).decode().rstrip("=")
    url = f"https://developer.api.autodesk.com/modelderivative/v2/designdata/{encoded_urn}/manifest"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        manifest = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching manifest: {e}")
        return [vkt.OptionListElement(label="Error fetching manifest", value=None)]

    options = []
    # Find the main derivative with viewable geometry
    for derivative in manifest.get("derivatives", []):
        if derivative.get("outputType") in ["svf", "svf2"]:
            # Find the parent geometry nodes for both 3D and 2D
            for geometry_node in derivative.get("children", []):
                
                # --- MODIFIED LOGIC TO INCLUDE 2D ---
                # Check if the node is a geometry container for a 3D or 2D view
                if geometry_node.get("type") == "geometry" and geometry_node.get("role") in ["3d", "2d"]:
                    view_name = geometry_node.get("name")
                    view_guid = None
                    view_role = geometry_node.get("role") # '3d' or '2d'

                    # Search its children for the actual node with "type": "view"
                    for child_node in geometry_node.get("children", []):
                        if child_node.get("type") == "view":
                            view_guid = child_node.get("guid")
                            if child_node.get("name").startswith("Sheet:"):
                                view_name = child_node.get("name")
                            break # Found the correct view node
                    
                    if view_name and view_guid:
                        # I added this prefix but can be ommited
                        label_prefix = "[3D]" if view_role == "3d" else "[2D]"
                        options.append(vkt.OptionListElement(label=f"{label_prefix} {view_name}", value=view_guid))

    if not options:
        return [vkt.OptionListElement(label="No 3D or 2D views found in manifest", value=None)]
    
    
    return options

@vkt.memoize
def get_viewable_files_dict(params, **kwargs) -> dict[str, dict[str, str]]:
    """ Return a dictionary with keys -> file name, and vals as a dict of file name and urn"""
    integration = vkt.external.OAuth2Integration("aps-integration-1")
    token = integration.get_access_token()
    if not params.hubs:
        # Return an empty dict to avoid NoneType issues upstream
        return {}
    hub_id = aps_helpers.get_hub_id_by_name(token, params.hubs)
    viewable_dict = aps_helpers.get_all_cad_file_from_hub(token=token, hub_id=hub_id) or {}
    return viewable_dict

def get_hub_list(params, **kwargs) -> list[str]:
    integration = vkt.external.OAuth2Integration("aps-integration-1")
    token = integration.get_access_token()
    hub_names = aps_helpers.get_hub_names(token)
    return hub_names if hub_names else ["No hubs found"]

def get_viewable_files_names(params, **kwargs) -> list[str]:
    if not params.hubs:
        return ["Select a hub first!"]
    print(params.hubs)
    viewable_file_dict = get_viewable_files_dict(params, **kwargs)
    if viewable_file_dict:
        return list(viewable_file_dict.keys())
    return ["No viewable files in the hub"]


class Parametrization(vkt.Parametrization):
    title = vkt.Text("# Viewables APS - Viktor Integration")
    hubs = vkt.OptionField("Avaliable Hubs", options=get_hub_list)
    # Provide a list of file names as options; never return None
    viewable_file = vkt.OptionField("Available Viewables", options=get_viewable_files_names)
    br = vkt.LineBreak()
    select_view = vkt.OptionField("Select View", options=get_view_options)

class Controller(vkt.Controller):
    parametrization = Parametrization(width=40)

    @vkt.WebView("Forge Viewer", duration_guess=5)
    def viewer_page(self, params, **kwargs):
        """WebView that loads the Forge Viewer with the selected view GUID."""
        selected_guid = params.select_view
        print(selected_guid)
        integration = vkt.external.OAuth2Integration("aps-integration-1")
        token = integration.get_access_token()
        viewable_file = params.viewable_file
        viewable_dict = get_viewable_files_dict(params, **kwargs)
        urn = viewable_dict.get(viewable_file, {}).get("urn")

        encoded_urn = base64.urlsafe_b64encode(urn.encode()).decode().rstrip("=")

        html = (Path(__file__).parent / "ViewableViewer.html").read_text() # Adjust path if needed
        html = html.replace("APS_TOKEN_PLACEHOLDER", token)
        html = html.replace("URN_PLACEHOLDER", encoded_urn) # Pass the ENCODED urn
        html = html.replace("VIEW_GUID_PLACEHOLDER", selected_guid or "")
        
        return vkt.WebResult(html=html)