from discord.ext import commands
import discord
from discord import app_commands
from helpers.embed_helpers import create_basic_embed, create_error_embed, create_success_embed
from typing import Optional, List
from sqlalchemy import select, or_
from models.database import Organization, OrganizationMember, PaymentSchedule, IntervalType

class Organizations(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db_manager

    async def get_user_organizations(self, user_id: str) -> List[Organization]:
        """Helper method to get organizations for a user"""
        async with self.db.session() as session:
            # Get orgs where user is owner or member
            orgs = await session.execute(
                select(Organization).where(
                    or_(
                        Organization.owner_id == str(user_id),
                        Organization.id.in_(
                            select(OrganizationMember.organization_id).where(
                                OrganizationMember.user_id == str(user_id)
                            )
                        )
                    )
                )
            )
            return orgs.scalars().all()

    async def get_organization_members(self, org_id: int) -> List[OrganizationMember]:
        """Helper method to get members of an organization"""
        async with self.db.session() as session:
            members = await session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == org_id
                )
            )
            return members.scalars().all()

    async def get_organization_schedules(self, org_id: int) -> List[PaymentSchedule]:
        """Helper method to get payment schedules for an organization"""
        async with self.db.session() as session:
            schedules = await session.execute(
                select(PaymentSchedule).where(
                    PaymentSchedule.organization_id == org_id
                )
            )
            return schedules.scalars().all()

    @app_commands.command(name="add_member", description="Add a member to your organization")
    @app_commands.describe(
        user="The user to add to your organization",
        organization="The organization to add them to"
    )
    async def add_member(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member,
        organization: str
    ):
        session = self.db.Session()
        try:
            # Check if org exists and user is owner
            org = session.query(Organization).filter_by(
                name=organization,
                owner_id=str(interaction.user.id)
            ).first()
            
            if not org:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Not Found",
                        description="You don't own an organization with that name."
                    ),
                    ephemeral=True
                )
                return

            # Check if user is already a member
            existing_member = session.query(OrganizationMember).filter_by(
                organization_id=org.id,
                user_id=str(user.id)
            ).first()
            
            if existing_member:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Already Member",
                        description=f"{user.mention} is already a member of {organization}!"
                    ),
                    ephemeral=True
                )
                return

            # Add the member
            member = OrganizationMember(
                organization_id=org.id,
                user_id=str(user.id)
            )
            session.add(member)
            session.commit()

            await interaction.response.send_message(
                embed=create_success_embed(
                    title="Member Added",
                    description=f"Successfully added {user.mention} to {organization}!"
                ),
                ephemeral=True
            )
        finally:
            session.close()

    @app_commands.command(name="remove_member", description="Remove a member from your organization")
    @app_commands.describe(
        user="The user to remove from your organization",
        organization="The organization to remove them from"
    )
    async def remove_member(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member,
        organization: str
    ):
        session = self.db.Session()
        try:
            # Check if org exists and user is owner
            org = session.query(Organization).filter_by(
                name=organization,
                owner_id=str(interaction.user.id)
            ).first()
            
            if not org:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Not Found",
                        description="You don't own an organization with that name."
                    ),
                    ephemeral=True
                )
                return

            # Find and remove the member
            member = session.query(OrganizationMember).filter_by(
                organization_id=org.id,
                user_id=str(user.id)
            ).first()
            
            if not member:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Not a Member",
                        description=f"{user.mention} is not a member of {organization}!"
                    ),
                    ephemeral=True
                )
                return

            session.delete(member)
            session.commit()

            await interaction.response.send_message(
                embed=create_success_embed(
                    title="Member Removed",
                    description=f"Successfully removed {user.mention} from {organization}!"
                ),
                ephemeral=True
            )
        finally:
            session.close()

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Organizations(bot))