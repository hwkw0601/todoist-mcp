"""Local Todoist MCP server.

Phase 1 scaffold: a FastMCP server that starts over stdio with no tools yet.
Tools are added in later phases. Nothing is ever written to stdout except the
MCP protocol itself; all logging goes to stderr.
"""

import logging
import sys

from fastmcp import FastMCP

# Log to stderr only. stdout is reserved for the MCP (stdio) protocol — writing
# anything else there would corrupt the client connection.
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("todoist-mcp")

mcp = FastMCP("todoist-mcp")

# No tools yet — Phase 1 success is simply that the server launches and a client
# connects to an empty tool list.


def main() -> None:
    """Entry point: run the server over stdio."""
    logger.info("Starting todoist-mcp server (stdio, no tools yet)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
