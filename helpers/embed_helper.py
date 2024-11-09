import discord

def create_basic_embed(title: str, description: str, add_footer: bool = False) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue()
    )
    
    if add_footer:
        embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
        
    return embed 