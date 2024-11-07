from discord.ext import commands
import discord
from discord import app_commands
from helpers.embed_helpers import create_basic_embed, create_success_embed, create_error_embed

def is_admin():
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.points_manager = bot.points_manager

    @app_commands.guild_only()
    @app_commands.command(name="balance", description="Check your Points balance")
    async def check_balance(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            balance = await self.points_manager.get_balance(interaction.user.id)
            embed = create_basic_embed(
                title="Balance Check",
                description=f"Your current balance: **{balance:,}** Points"
            )
            embed.set_footer(text=f"Requested by {interaction.user.name}")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = create_error_embed(
                title="Error",
                description=f"Failed to check balance: {str(e)}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="tip", description="Tip Points to another user")
    @app_commands.describe(
        user="The user to tip",
        amount="Amount of Points to tip"
    )
    async def tip(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        
        if amount <= 0:
            embed = create_error_embed(
                title="Invalid Amount",
                description="Amount must be positive!"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
            
        if user.id == interaction.user.id:
            embed = create_error_embed(
                title="Invalid Recipient",
                description="You can't tip yourself!"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if user.bot:
            embed = create_error_embed(
                title="Invalid Recipient",
                description="You can't tip bots!"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        try:
            sender_balance = await self.points_manager.get_balance(interaction.user.id)
            if sender_balance < amount:
                embed = create_error_embed(
                    title="Insufficient Balance",
                    description=f"You don't have enough Points!\nYour balance: **{sender_balance:,}** Points"
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            success = await self.points_manager.transfer_points(
                interaction.user.id,
                user.id,
                amount
            )
            
            if success:
                embed = create_success_embed(
                    title="Tip Successful",
                    description=f"Successfully tipped **{amount:,}** Points to {user.mention}!"
                )
                embed.set_footer(text=f"From: {interaction.user.name}")
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = create_error_embed(
                    title="Transfer Failed",
                    description="Failed to transfer Points. Please try again later."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = create_error_embed(
                title="Error",
                description=f"Error processing tip: {str(e)}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="check", description="Check another user's Points balance")
    @app_commands.describe(user="The user to check")
    async def check_other(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        
        if user.bot:
            embed = create_error_embed(
                title="Invalid User",
                description="Bots don't have Points balances!"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        try:
            balance = await self.points_manager.get_balance(user.id)
            embed = create_basic_embed(
                title=f"Balance Check for {user.name}",
                description=f"Current balance: **{balance:,}** Points"
            )
            embed.set_footer(text=f"Checked by {interaction.user.name}")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = create_error_embed(
                title="Error",
                description=f"Failed to check balance: {str(e)}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="add", description="Add Points to a user's balance")
    @app_commands.describe(
        user="The user to add Points to",
        amount="Amount of Points to add"
    )
    @is_admin()
    async def add_points(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        
        if amount <= 0:
            embed = create_error_embed(
                title="Invalid Amount",
                description="Amount must be positive!"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
            
        if user.bot:
            embed = create_error_embed(
                title="Invalid Recipient",
                description="Cannot add Points to bots!"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        try:
            success = await self.points_manager.add_points(user.id, amount)
            if success:
                new_balance = await self.points_manager.get_balance(user.id)
                embed = create_success_embed(
                    title="Points Added",
                    description=f"Successfully added **{amount:,}** Points to {user.mention}\nNew balance: **{new_balance:,}** Points"
                )
                embed.set_footer(text=f"Added by {interaction.user.name}")
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = create_error_embed(
                    title="Operation Failed",
                    description="Failed to add Points. Please try again later."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = create_error_embed(
                title="Error",
                description=f"Error adding Points: {str(e)}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="remove", description="Remove Points from a user's balance")
    @app_commands.describe(
        user="The user to remove Points from",
        amount="Amount of Points to remove"
    )
    @is_admin()
    async def remove_points(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        
        if amount <= 0:
            embed = create_error_embed(
                title="Invalid Amount",
                description="Amount must be positive!"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
            
        if user.bot:
            embed = create_error_embed(
                title="Invalid Target",
                description="Cannot remove Points from bots!"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        try:
            current_balance = await self.points_manager.get_balance(user.id)
            if current_balance < amount:
                embed = create_error_embed(
                    title="Insufficient Balance",
                    description=f"User only has **{current_balance:,}** Points!\nCannot remove **{amount:,}** Points."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            success = await self.points_manager.remove_points(user.id, amount)
            if success:
                new_balance = await self.points_manager.get_balance(user.id)
                embed = create_success_embed(
                    title="Points Removed",
                    description=f"Successfully removed **{amount:,}** Points from {user.mention}\nNew balance: **{new_balance:,}** Points"
                )
                embed.set_footer(text=f"Removed by {interaction.user.name}")
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = create_error_embed(
                    title="Operation Failed",
                    description="Failed to remove Points. Please try again later."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = create_error_embed(
                title="Error",
                description=f"Error removing Points: {str(e)}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @add_points.error
    @remove_points.error
    async def admin_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = create_error_embed(
                title="Permission Denied",
                description="You don't have permission to use this command!"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))