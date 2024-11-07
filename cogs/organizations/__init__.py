from discord.ext import commands, tasks
import discord
from discord import app_commands
from models.database import Organization, OrganizationMember, PaymentSchedule, IntervalType
from datetime import datetime, timedelta

def is_admin():
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

class Organizations(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db_manager.Session()
        self.points_manager = bot.points_manager
        self.process_payments.start()

    def cog_unload(self):
        self.process_payments.cancel()

    @app_commands.guild_only()
    @app_commands.command(name="create_org", description="Create a new organization")
    @app_commands.describe(name="Name of the organization")
    async def create_org(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        
        # Check if org already exists
        existing_org = self.db.query(Organization).filter_by(name=name).first()
        if existing_org:
            await interaction.followup.send("An organization with this name already exists!", ephemeral=True)
            return

        org = Organization(name=name, owner_id=str(interaction.user.id))
        self.db.add(org)
        self.db.commit()

        await interaction.followup.send(f"Organization '{name}' created successfully!", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="delete_org", description="Delete an organization")
    @app_commands.describe(name="Name of the organization to delete")
    async def delete_org(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        
        org = self.db.query(Organization).filter_by(name=name).first()
        if not org:
            await interaction.followup.send("Organization not found!", ephemeral=True)
            return

        if str(interaction.user.id) != org.owner_id:
            await interaction.followup.send("Only the organization owner can delete it!", ephemeral=True)
            return

        self.db.delete(org)
        self.db.commit()

        await interaction.followup.send(f"Organization '{name}' has been deleted.", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="add_member", description="Add a member to an organization")
    @app_commands.describe(
        org_name="Name of the organization",
        user="User to add to the organization"
    )
    async def add_member(self, interaction: discord.Interaction, org_name: str, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        
        org = self.db.query(Organization).filter_by(name=org_name).first()
        if not org:
            await interaction.followup.send("Organization not found!", ephemeral=True)
            return

        if str(interaction.user.id) != org.owner_id:
            await interaction.followup.send("Only the organization owner can add members!", ephemeral=True)
            return

        # Check if user is already a member
        existing_member = self.db.query(OrganizationMember).filter_by(
            organization_id=org.id,
            user_id=str(user.id)
        ).first()
        
        if existing_member:
            await interaction.followup.send("User is already a member of this organization!", ephemeral=True)
            return

        member = OrganizationMember(organization_id=org.id, user_id=str(user.id))
        self.db.add(member)
        self.db.commit()

        await interaction.followup.send(f"Added {user.mention} to organization '{org_name}'!", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="remove_member", description="Remove a member from an organization")
    @app_commands.describe(
        org_name="Name of the organization",
        user="User to remove from the organization"
    )
    async def remove_member(self, interaction: discord.Interaction, org_name: str, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        
        org = self.db.query(Organization).filter_by(name=org_name).first()
        if not org:
            await interaction.followup.send("Organization not found!", ephemeral=True)
            return

        if str(interaction.user.id) != org.owner_id:
            await interaction.followup.send("Only the organization owner can remove members!", ephemeral=True)
            return

        member = self.db.query(OrganizationMember).filter_by(
            organization_id=org.id,
            user_id=str(user.id)
        ).first()
        
        if not member:
            await interaction.followup.send("User is not a member of this organization!", ephemeral=True)
            return

        self.db.delete(member)
        self.db.commit()

        await interaction.followup.send(f"Removed {user.mention} from organization '{org_name}'!", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="schedule_payment", description="Schedule automated payments")
    @app_commands.describe(
        org_name="Name of the organization",
        user="User to receive payments (optional)",
        amount="Amount of Points to pay",
        interval_type="Payment interval type",
        interval_value="Interval value (in selected units)"
    )
    @app_commands.choices(interval_type=[
        app_commands.Choice(name="Minutes", value="minutes"),
        app_commands.Choice(name="Hours", value="hours"),
        app_commands.Choice(name="Days", value="days"),
    ])
    async def schedule_payment(
        self, 
        interaction: discord.Interaction, 
        org_name: str, 
        amount: int, 
        interval_type: str,
        interval_value: int,
        user: discord.Member = None
    ):
        await interaction.response.defer(ephemeral=True)
        
        org = self.db.query(Organization).filter_by(name=org_name).first()
        if not org:
            await interaction.followup.send("Organization not found!", ephemeral=True)
            return

        if str(interaction.user.id) != org.owner_id:
            await interaction.followup.send("Only the organization owner can schedule payments!", ephemeral=True)
            return

        schedule = PaymentSchedule(
            organization_id=org.id,
            user_id=str(user.id) if user else None,
            amount=amount,
            interval_type=IntervalType(interval_type),
            interval_value=interval_value
        )
        
        self.db.add(schedule)
        self.db.commit()

        target = user.mention if user else f"all members of '{org_name}'"
        await interaction.followup.send(
            f"Payment schedule created: {amount:,} Points to {target} "
            f"every {interval_value} {interval_type}",
            ephemeral=True
        )

    @app_commands.guild_only()
    @app_commands.command(name="list_org_members", description="List all members of an organization")
    @app_commands.describe(org_name="Name of the organization")
    async def list_org_members(self, interaction: discord.Interaction, org_name: str):
        await interaction.response.defer(ephemeral=True)
        
        org = self.db.query(Organization).filter_by(name=org_name).first()
        if not org:
            await interaction.followup.send("Organization not found!", ephemeral=True)
            return

        members = self.db.query(OrganizationMember).filter_by(organization_id=org.id).all()
        if not members:
            await interaction.followup.send(f"No members found in organization '{org_name}'", ephemeral=True)
            return

        member_list = []
        for member in members:
            user = interaction.guild.get_member(int(member.user_id))
            if user:
                member_list.append(f"• {user.mention}")

        embed = discord.Embed(
            title=f"Members of {org_name}",
            description="\n".join(member_list) if member_list else "No active members found",
            color=discord.Color.blue()
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tasks.loop(minutes=1)
    async def process_payments(self):
        try:
            schedules = self.db.query(PaymentSchedule).all()
            for schedule in schedules:
                # Calculate next payment time
                delta = timedelta(**{schedule.interval_type.value: schedule.interval_value})
                next_payment = schedule.last_paid_at + delta
                
                if datetime.utcnow() >= next_payment:
                    if schedule.user_id:  # Individual payment
                        success = await self.points_manager.add_points(
                            int(schedule.user_id),
                            schedule.amount
                        )
                        if success:
                            schedule.last_paid_at = datetime.utcnow()
                    else:  # Organization-wide payment
                        members = self.db.query(OrganizationMember).filter_by(
                            organization_id=schedule.organization_id
                        ).all()
                        
                        for member in members:
                            success = await self.points_manager.add_points(
                                int(member.user_id),
                                schedule.amount
                            )
                            if success:
                                schedule.last_paid_at = datetime.utcnow()
                    
                    self.db.commit()
        except Exception as e:
            print(f"Error processing payments: {e}")

    @process_payments.before_loop
    async def before_process_payments(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Organizations(bot))