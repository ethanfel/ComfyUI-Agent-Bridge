from src.bridge import mcp_server


def test_build_server_registers_tools():
    mcp = mcp_server.build_server()
    # FastMCP stores tools; assert our names are present
    tool_names = mcp_server.registered_tool_names(mcp)
    for name in ["comfy_pull", "comfy_push", "comfy_list_channels",
                 "comfy_run_workflow", "comfy_get_result"]:
        assert name in tool_names


def test_start_is_idempotent():
    mcp_server.start_in_background(port=0, _test_no_serve=True)
    mcp_server.start_in_background(port=0, _test_no_serve=True)  # no crash
