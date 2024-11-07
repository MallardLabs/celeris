from discord import Embed, Color

def create_basic_embed(title: str, description: str = None) -> Embed:
    return Embed(
        title=title,
        description=description,
        color=Color.blue()
    )

def create_success_embed(title: str, description: str = None) -> Embed:
    return Embed(
        title=title,
        description=description,
        color=Color.green()
    )

def create_error_embed(title: str, description: str = None) -> Embed:
    return Embed(
        title=title,
        description=description,
        color=Color.red()
    )

def create_schedule_embed(schedule, organization, remaining_points: int = None) -> Embed:
    embed = Embed(
        title=f"Payment Schedule for {organization.name}",
        color=Color.blue()
    )
    
    embed.add_field(
        name="Payment Amount", 
        value=f"{schedule.amount:,} Points", 
        inline=True
    )
    embed.add_field(
        name="Interval", 
        value=f"{schedule.interval_value} {schedule.interval_type.value}", 
        inline=True
    )
    
    if remaining_points is not None:
        embed.add_field(
            name="Remaining Points", 
            value=f"{remaining_points:,} Points", 
            inline=True
        )
        
    if schedule.user_id:
        embed.add_field(
            name="Type", 
            value="Individual Payment", 
            inline=True
        )
    else:
        embed.add_field(
            name="Type", 
            value="Organization-wide Payment", 
            inline=True
        )
    
    return embed 