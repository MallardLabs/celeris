from discord import Embed, Color

def calculate_schedule_progress(points_paid: int, total_points: int) -> tuple[float, str]:
    """Calculate progress percentage and generate progress bar"""
    progress = (points_paid / total_points) * 100
    filled_blocks = int((progress / 100) * 10)
    empty_blocks = 10 - filled_blocks
    progress_bar = '█' * filled_blocks + '░' * empty_blocks
    return progress, progress_bar

def create_basic_embed(title: str, description: str = None, add_footer: bool = False) -> Embed:
    embed = Embed(
        title=title,
        description=description,
        color=Color.blue()
    )
    if add_footer:
        embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
    return embed

def create_success_embed(title: str, description: str = None, add_footer: bool = False) -> Embed:
    embed = Embed(
        title=title,
        description=description,
        color=Color.green()
    )
    if add_footer:
        embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
    return embed

def create_error_embed(title: str, description: str = None, add_footer: bool = False) -> Embed:
    embed = Embed(
        title=title,
        description=description,
        color=Color.red()
    )
    if add_footer:
        embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
    return embed

def create_schedule_embed(schedule, organization, remaining_points: int = None) -> Embed:
    embed = Embed(
        title=f"Payment Schedule for {organization.name}",
        color=Color.blue()
    )
    
    # ... (existing fields remain the same) ...
    
    embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
    return embed 