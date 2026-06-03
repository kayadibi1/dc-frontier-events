import asyncio

from aggregator.render import close_render, render


def test_render_returns_html_and_never_raises():
    async def go():
        html = await render("data:text/html,<h1 id=x>Hi there</h1>", wait_for="#x")
        assert "Hi there" in html
        bad = await render("http://nonexistent.invalid.localhost:1/")
        assert bad == ""                         # failures return "" not raise
        await close_render()

    asyncio.run(go())
