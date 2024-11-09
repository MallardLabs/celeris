from discord.ext import commands
import discord
from discord import app_commands
from helpers.embed_helpers import create_basic_embed, create_error_embed, create_success_embed
from typing import Optional, List
from sqlalchemy import select, or_
from models.database import Organization, OrganizationMember, PaymentSchedule, IntervalType
from datetime import datetime

class ConfirmationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)  # 60 second timeout
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        self.value = False
        self.stop()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, emoji="🏠")
    async def back_to_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = create_basic_embed(
            title="Welcome to Celeris",
            description=(
                "### Get Started\n"
                "Create and manage organizations, automate payments, and more!\n\n"
                "**🔑 Key Features**\n"
                "• Create organizations\n"
                "• Set up automated payments\n"
                "• Manage members and roles\n"
                "• Track payment history\n\n"
                "**💡 Quick Start**\n"
                "Click 'Create Organization' to begin!"
            )
        )
        embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
        view = StartView()
        await interaction.response.edit_message(embed=embed, view=view)

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

    @app_commands.command(
        name="add_member",
        description="Add a user to an organization (Owner only)"
    )
    @app_commands.describe(
        organization_name="Name of the organization",
        user="The user to add to the organization"
    )
    async def add_member(
        self,
        interaction: discord.Interaction,
        organization_name: str,
        user: discord.Member
    ):
        session = self.db.Session()
        try:
            # Check if org exists and user is owner
            org = session.query(Organization).filter_by(name=organization_name).first()
            
            if not org:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Organization Not Found",
                        description=f"No organization named '{organization_name}' exists."
                    ),
                    ephemeral=True
                )
                return

            # Verify the command user is the owner
            if str(interaction.user.id) != org.owner_id:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Permission Denied",
                        description="You must be the organization owner to add members."
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
                        title="Already a Member",
                        description=f"{user.mention} is already a member of {organization_name}!"
                    ),
                    ephemeral=True
                )
                return

            # Add the new member
            new_member = OrganizationMember(
                organization_id=org.id,
                user_id=str(user.id)
            )
            session.add(new_member)
            session.commit()

            # Send success message
            embed = create_success_embed(
                title="Member Added",
                description=(
                    f"Successfully added {user.mention} to **{organization_name}**!\n\n"
                    "**Organization Details**\n"
                    f"• Name: {org.name}\n"
                    f"• Owner: <@{org.owner_id}>\n"
                    f"• Added: <t:{int(datetime.utcnow().timestamp())}:R>"
                )
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            session.rollback()
            await interaction.response.send_message(
                embed=create_error_embed(
                    title="Error",
                    description=f"An error occurred: {str(e)}"
                ),
                ephemeral=True
            )
        finally:
            session.close()

    @app_commands.command(
        name="remove_member",
        description="Remove a member from your organization (Owner only)"
    )
    @app_commands.describe(
        organization_name="Name of the organization",
        user="The user to remove from the organization"
    )
    async def remove_member(
        self,
        interaction: discord.Interaction,
        organization_name: str,
        user: discord.Member
    ):
        session = self.db.Session()
        try:
            # Check if org exists and user is owner
            org = session.query(Organization).filter_by(name=organization_name).first()
            
            if not org:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Organization Not Found",
                        description=f"No organization named '{organization_name}' exists."
                    ),
                    ephemeral=True
                )
                return

            # Verify the command user is the owner
            if str(interaction.user.id) != org.owner_id:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Permission Denied",
                        description="You must be the organization owner to remove members."
                    ),
                    ephemeral=True
                )
                return

            # Can't remove the owner
            if str(user.id) == org.owner_id:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Cannot Remove Owner",
                        description="The organization owner cannot be removed. Use `/transfer_ownership` to change ownership first."
                    ),
                    ephemeral=True
                )
                return

            # Check if user is a member
            member = session.query(OrganizationMember).filter_by(
                organization_id=org.id,
                user_id=str(user.id)
            ).first()
            
            if not member:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Not a Member",
                        description=f"{user.mention} is not a member of {organization_name}!"
                    ),
                    ephemeral=True
                )
                return

            # Remove member from payment schedules
            session.query(PaymentScheduleMember).filter(
                PaymentScheduleMember.schedule_id.in_(
                    session.query(PaymentSchedule.id).filter_by(organization_id=org.id)
                ),
                PaymentScheduleMember.user_id == str(user.id)
            ).delete(synchronize_session=False)

            # Remove the member
            session.delete(member)
            session.commit()

            # Send success message
            embed = create_success_embed(
                title="Member Removed",
                description=(
                    f"Successfully removed {user.mention} from **{organization_name}**!\n\n"
                    "**Organization Details**\n"
                    f"• Name: {org.name}\n"
                    f"• Owner: <@{org.owner_id}>\n"
                    f"• Removed: <t:{int(datetime.utcnow().timestamp())}:R>"
                )
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            session.rollback()
            await interaction.response.send_message(
                embed=create_error_embed(
                    title="Error",
                    description=f"An error occurred: {str(e)}"
                ),
                ephemeral=True
            )
        finally:
            session.close()

    @app_commands.command(
        name="transfer_ownership",
        description="Transfer ownership of your organization to another member"
    )
    @app_commands.describe(
        organization_name="Name of the organization",
        new_owner="The user to transfer ownership to"
    )
    async def transfer_ownership(
        self,
        interaction: discord.Interaction,
        organization_name: str,
        new_owner: discord.Member
    ):
        session = self.db.Session()
        try:
            # Check if org exists and user is owner
            org = session.query(Organization).filter_by(name=organization_name).first()
            
            if not org:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Organization Not Found",
                        description=f"No organization named '{organization_name}' exists."
                    ),
                    ephemeral=True
                )
                return

            # Verify the command user is the owner
            if str(interaction.user.id) != org.owner_id:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Permission Denied",
                        description="You must be the organization owner to transfer ownership."
                    ),
                    ephemeral=True
                )
                return

            # Check if new owner is already a member
            member = session.query(OrganizationMember).filter_by(
                organization_id=org.id,
                user_id=str(new_owner.id)
            ).first()

            if not member:
                # Add new owner as member
                member = OrganizationMember(
                    organization_id=org.id,
                    user_id=str(new_owner.id)
                )
                session.add(member)

            # Create confirmation view
            confirm_view = ConfirmationView()
            confirm_embed = create_basic_embed(
                title="Confirm Ownership Transfer",
                description=(
                    f"Are you sure you want to transfer ownership of **{organization_name}** to {new_owner.mention}?\n\n"
                    "**⚠️ Warning**\n"
                    "• This action cannot be undone\n"
                    "• You will lose owner privileges\n"
                    "• The new owner will have full control"
                )
            )
            
            await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=True)
            
            # Wait for confirmation
            await confirm_view.wait()
            if confirm_view.value:
                old_owner = org.owner_id
                org.owner_id = str(new_owner.id)
                session.commit()

                success_embed = create_success_embed(
                    title="Ownership Transferred",
                    description=(
                        f"Successfully transferred ownership of **{organization_name}**!\n\n"
                        "**Organization Details**\n"
                        f"• Name: {org.name}\n"
                        f"• Previous Owner: <@{old_owner}>\n"
                        f"• New Owner: {new_owner.mention}\n"
                        f"• Transferred: <t:{int(datetime.utcnow().timestamp())}:R>"
                    )
                )
                await interaction.edit_original_response(embed=success_embed, view=None)

                # Try to notify new owner
                try:
                    notify_embed = create_success_embed(
                        title="Organization Ownership Received",
                        description=(
                            f"You are now the owner of **{organization_name}**!\n\n"
                            "**Organization Details**\n"
                            f"• Name: {org.name}\n"
                            f"• Previous Owner: <@{old_owner}>\n"
                            f"• Transferred: <t:{int(datetime.utcnow().timestamp())}:R>\n\n"
                            "**Available Commands**\n"
                            "• `/add_member` - Add new members\n"
                            "• `/remove_member` - Remove members\n"
                            "• `/transfer_ownership` - Transfer ownership"
                        )
                    )
                    await new_owner.send(embed=notify_embed)
                except:
                    pass  # Ignore if DM fails

            else:
                cancel_embed = create_basic_embed(
                    title="Transfer Cancelled",
                    description="The ownership transfer was cancelled."
                )
                await interaction.edit_original_response(embed=cancel_embed, view=None)

        except Exception as e:
            session.rollback()
            await interaction.followup.send(
                embed=create_error_embed(
                    title="Error",
                    description=f"An error occurred: {str(e)}"
                ),
                ephemeral=True
            )
        finally:
            session.close()

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Organizations(bot))