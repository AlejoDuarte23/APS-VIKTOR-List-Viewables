from pathlib import Path
import base64
import viktor as vkt  # type: ignore
import aps_helpers


class APSView(vkt.WebView):
    pass

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

class APSresult(vkt.WebResult):
    def __init__(self, urn: str, token: str):
        html = (Path(__file__).parent / "ApsViewer.html").read_text()
        html = html.replace("APS_TOKEN_PLACEHOLDER", token)
        # Encode URN to URL-safe base64 without padding for the viewer
        encoded_urn = base64.urlsafe_b64encode(urn.encode()).decode().rstrip("=")
        html = html.replace("URN_PLACEHOLDER", encoded_urn)
        super().__init__(html=html)


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
    title = vkt.Text("# Data Exchange - Viktor Integration")
    hubs = vkt.OptionField("Avaliable Hubs", options=get_hub_list)
    # Provide a list of file names as options; never return None
    viewable_file = vkt.OptionField("Available Viewables", options=get_viewable_files_names)


class Controller(vkt.Controller):
    parametrization = Parametrization(width=40)

    @APSView("Model Viewer", duration_guess=40)
    def get_file_viewable(params, **kwargs) -> APSresult | None:
        integration = vkt.external.OAuth2Integration("aps-integration-1")
        token = integration.get_access_token()
        file_viewable_dict = get_viewable_files_dict(params, **kwargs)
        if file_viewable_dict:
            urn = file_viewable_dict.get(params.viewable_file, {}).get("urn")
            if urn:
                return APSresult(urn=urn, token=token)
