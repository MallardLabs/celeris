from discord.ext import commands
import discord
from discord import app_commands
from helpers.embed_helpers import create_basic_embed, create_error_embed, create_success_embed
from typing import Optional, List
from sqlalchemy import select, or_
from models.database import Organization, OrganizationMember, PaymentSchedule, IntervalType, PaymentScheduleMember
from datetime import datetime

class ConfirmationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60.0)
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()

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
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db_manager

    @app_commands.command(
        name="add_to_org",
        description="Add a user to an organization (Owner only)"
    )
    @app_commands.describe(
        organization_name="Name of the organization",
        user="The user to add to the organization"
    )
    async def add_to_org(
        self,
        interaction: discord.Interaction,
        organization_name: str,
        user: discord.Member
    ):
        session = self.bot.db_manager.Session()
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
        name="remove_from_org",
        description="Remove a user from an organization"
    )
    @app_commands.describe(
        organization_name="Name of the organization",
        user="User to remove from the organization"
    )
    async def remove_from_org(
        self,
        interaction: discord.Interaction,
        organization_name: str,
        user: discord.Member
    ):
        await interaction.response.defer(ephemeral=True)
        
        session = self.bot.db_manager.Session()
        try:
            # Find the organization
            org = session.query(Organization).filter_by(name=organization_name).first()
            if not org:
                raise ValueError(f"Organization '{organization_name}' not found!")

            # Check if user is the owner
            if str(interaction.user.id) != org.owner_id:
                raise ValueError("Only the organization owner can remove members!")

            # Find the member
            member = session.query(OrganizationMember).filter_by(
                organization_id=org.id,
                user_id=str(user.id)
            ).first()
            
            if not member:
                raise ValueError(f"{user.name} is not a member of {organization_name}!")

            # Remove member from active payment schedules
            active_schedules = session.query(PaymentSchedule).filter_by(
                organization_id=org.id
            ).all()
            
            removed_from_schedules = 0
            for schedule in active_schedules:
                schedule_member = session.query(PaymentScheduleMember).filter_by(
                    schedule_id=schedule.id,
                    user_id=str(user.id)
                ).first()
                if schedule_member:
                    session.delete(schedule_member)
                    removed_from_schedules += 1

            # Remove the member from the organization
            joined_at = member.joined_at  # Store for the success message
            session.delete(member)
            session.commit()

            embed = create_success_embed(
                title="Member Removed",
                description=(
                    f"Successfully removed {user.mention} from **{organization_name}**!\n\n"
                    "**📊 Updates**\n"
                    "• Removed from organization roster\n"
                    f"• Removed from {removed_from_schedules} active payment schedule(s)\n"
                    f"• Was a member for: {discord.utils.format_dt(joined_at, style='R')}"
                )
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        except ValueError as e:
            await interaction.followup.send(
                embed=create_error_embed(title="Invalid Input", description=str(e)),
                ephemeral=True
            )
        except Exception as e:
            session.rollback()
            await interaction.followup.send(
                embed=create_error_embed(title="Error", description=f"An error occurred: {str(e)}"),
                ephemeral=True
            )
        finally:
            session.close()

    @app_commands.command(
        name="cancel_schedule",
        description="Cancel an existing payment schedule"
    )
    @app_commands.describe(
        schedule_id="The ID of the schedule to cancel"
    )
    async def cancel_schedule(
        self,
        interaction: discord.Interaction,
        schedule_id: int
    ):
        await interaction.response.defer(ephemeral=True)
        
        session = self.bot.db_manager.Session()
        try:
            # Find the schedule
            schedule = session.query(PaymentSchedule).filter_by(id=schedule_id).first()
            if not schedule:
                raise ValueError(f"Schedule #{schedule_id} not found!")

            # Check permissions
            if schedule.organization_id:
                # Organization schedule
                org = session.query(Organization).filter_by(id=schedule.organization_id).first()
                if str(interaction.user.id) != org.owner_id:
                    raise ValueError("Only the organization owner can cancel this schedule!")
            else:
                # Individual schedule
                if str(interaction.user.id) != schedule.created_by:
                    raise ValueError("Only the schedule creator can cancel this schedule!")

            # Create confirmation view
            confirm_view = ConfirmationView()
            confirm_embed = create_basic_embed(
                title="Confirm Schedule Cancellation",
                description=(
                    f"Are you sure you want to cancel payment schedule **#{schedule_id}**?\n\n"
                    "**Schedule Details**\n"
                    f"• Amount per payment: {schedule.amount:,} points\n"
                    f"• Points paid: {schedule.points_paid:,}/{schedule.total_points:,}\n"
                    f"• Created: {discord.utils.format_dt(schedule.created_at, style='R')}\n\n"
                    "**⚠️ Warning**\n"
                    "• This action cannot be undone\n"
                    "• Remaining points will not be distributed\n"
                    "• All schedule data will be deleted"
                )
            )
            
            await interaction.followup.send(embed=confirm_embed, view=confirm_view, ephemeral=True)
            
            # Wait for confirmation
            await confirm_view.wait()
            
            if confirm_view.value:
                # Remove schedule members first
                session.query(PaymentScheduleMember).filter_by(
                    schedule_id=schedule.id
                ).delete()

                # Store info for success message
                points_remaining = schedule.total_points - schedule.points_paid
                duration = discord.utils.format_dt(schedule.created_at, style='R')

                # Remove the schedule
                session.delete(schedule)
                session.commit()

                success_embed = create_success_embed(
                    title="Schedule Cancelled",
                    description=(
                        f"Successfully cancelled payment schedule **#{schedule_id}**!\n\n"
                        "** Final Statistics**\n"
                        f"• Total points distributed: {schedule.points_paid:,}\n"
                        f"• Remaining points: {points_remaining:,}\n"
                        f"• Active duration: {duration} to now"
                    )
                )
                await interaction.edit_original_response(embed=success_embed, view=None)
            else:
                await interaction.edit_original_response(
                    embed=create_basic_embed(
                        title="Cancellation Aborted",
                        description="The schedule cancellation was cancelled."
                    ),
                    view=None
                )

        except ValueError as e:
            await interaction.followup.send(
                embed=create_error_embed(title="Invalid Input", description=str(e)),
                ephemeral=True
            )
        except Exception as e:
            session.rollback()
            await interaction.followup.send(
                embed=create_error_embed(title="Error", description=f"An error occurred: {str(e)}"),
                ephemeral=True
            )
        finally:
            session.close()

    @app_commands.command(
        name="transfer_org_ownership",
        description="Transfer ownership of an organization to another user"
    )
    @app_commands.describe(
        organization_name="Name of the organization",
        new_owner="User to transfer ownership to"
    )
    async def transfer_org_ownership(
        self,
        interaction: discord.Interaction,
        organization_name: str,
        new_owner: discord.Member
    ):
        await interaction.response.defer(ephemeral=True)
        
        session = self.bot.db_manager.Session()
        try:
            # Find the organization
            org = session.query(Organization).filter_by(name=organization_name).first()
            if not org:
                raise ValueError(f"Organization '{organization_name}' not found!")

            # Check if user is the current owner
            if str(interaction.user.id) != org.owner_id:
                raise ValueError("Only the organization owner can transfer ownership!")

            # Check if new owner is already a member
            member = session.query(OrganizationMember).filter_by(
                organization_id=org.id,
                user_id=str(new_owner.id)
            ).first()
            
            if not member:
                raise ValueError(f"{new_owner.name} must be a member of the organization first!")

            # Store old owner info for message
            old_owner = await self.bot.fetch_user(int(org.owner_id))

            # Update ownership
            org.owner_id = str(new_owner.id)
            session.commit()

            embed = create_success_embed(
                title="Ownership Transferred",
                description=(
                    f"Successfully transferred ownership of **{organization_name}**!\n\n"
                    "**📊 Details**\n"
                    f"• Previous Owner: {old_owner.mention}\n"
                    f"• New Owner: {new_owner.mention}\n"
                    f"• Transferred: <t:{int(datetime.utcnow().timestamp())}:R>"
                )
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        except ValueError as e:
            await interaction.followup.send(
                embed=create_error_embed(title="Invalid Input", description=str(e)),
                ephemeral=True
            )
        finally:
            session.close()

    @app_commands.command(
        name="pay_org",
        description="Create an automated payment schedule for an organization"
    )
    @app_commands.describe(
        organization_name="Name of the organization",
        amount="Amount of points per payment",
        interval_value="How often to make payments (e.g., 24)",
        interval_type="Time unit for interval (s/m/h/d/mm)",
        total_points="Total points to distribute over time"
    )
    async def pay_org(
        self,
        interaction: discord.Interaction,
        organization_name: str,
        amount: int,
        interval_value: int,
        interval_type: str,
        total_points: int
    ):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validate inputs
            if amount <= 0 or interval_value <= 0 or total_points <= 0:
                raise ValueError("All numerical values must be positive!")

            valid_intervals = [t.value for t in IntervalType]
            if interval_type.lower() not in valid_intervals:
                raise ValueError(f"Invalid interval type! Use: {', '.join(valid_intervals)}")

            if total_points < amount:
                raise ValueError("Total points must be greater than or equal to amount per payment!")

            session = self.bot.db_manager.Session()
            try:
                # Get organization
                org = session.query(Organization).filter_by(name=organization_name).first()
                if not org:
                    raise ValueError(f"Organization '{organization_name}' not found!")

                # Get members
                members = session.query(OrganizationMember).filter_by(organization_id=org.id).all()
                if not members:
                    raise ValueError("Organization has no members!")

                # Create payment schedule
                schedule = PaymentSchedule(
                    organization_id=org.id,
                    amount=amount,
                    interval_type=IntervalType(interval_type.lower()),
                    interval_value=interval_value,
                    total_points=total_points,
                    points_paid=0,
                    created_by=str(interaction.user.id),
                    last_paid_at=datetime.utcnow()
                )
                session.add(schedule)
                session.flush()

                # Add members to schedule
                for member in members:
                    schedule_member = PaymentScheduleMember(
                        schedule_id=schedule.id,
                        user_id=member.user_id
                    )
                    session.add(schedule_member)

                # Calculate how many payments are needed
                number_of_payments = total_points // amount
                if total_points % amount != 0:
                    number_of_payments += 1  # Add one more payment if there's a remainder

                # Calculate points per member for initial payment
                points_per_member = amount // len(members)
                successful_distributions = 0

                # Make initial payment
                for member in members:
                    try:
                        await self.bot.points_manager.add_points(
                            user_id=int(member.user_id),
                            amount=points_per_member
                        )
                        successful_distributions += 1

                        # Send DM notification
                        user = await self.bot.fetch_user(int(member.user_id))
                        progress_percentage = (points_per_member / total_points) * 100
                        filled_blocks = int((progress_percentage / 100) * 10)
                        empty_blocks = 10 - filled_blocks
                        progress_bar = '█' * filled_blocks + '░' * empty_blocks

                        dm_embed = create_success_embed(
                            title="Payment Received",
                            description=(
                                "**Organization Payment**\n"
                                "You've received a scheduled payment!\n\n"
                                f"💰 **Amount Received**\n{points_per_member:,} points\n\n"
                                f"📊 **Schedule Progress**\n{progress_bar} {progress_percentage:.1f}%\n"
                                f"({schedule.points_paid + points_per_member}/{schedule.total_points} points)\n\n"
                                f"⏰ **Payment Details**\n"
                                f"• Frequency: Every {interval_value} {interval_type}\n"
                                f"• Organization: {org.name}\n"
                                f"• Schedule ID: #{schedule.id}\n\n"
                                f"👥 Organization Payment • Automated Payment"
                            )
                        )
                        await user.send(embed=dm_embed)

                    except Exception as e:
                        print(f"Error distributing points to {member.user_id}: {e}")

                if successful_distributions > 0:
                    schedule.points_paid += points_per_member * successful_distributions
                    schedule.last_paid_at = datetime.utcnow()
                    session.commit()

                # Send success message
                embed = create_success_embed(
                    title="Payment Schedule Created",
                    description=(
                        f"Created organization payment schedule!\n\n"
                        "**📊 Schedule Details**\n"
                        f"• Amount per payment: {amount:,} points\n"
                        f"• Interval: Every {interval_value} {interval_type}\n"
                        f"• Members: {len(members)}\n"
                        f"• Points per member: {points_per_member:,}\n"
                        f"• Total points: {total_points:,}\n"
                        f"• Schedule ID: #{schedule.id}\n\n"
                        "**💰 Initial Payment**\n"
                        f"• Successful distributions: {successful_distributions}/{len(members)}\n"
                        f"• Points distributed: {schedule.points_paid:,}"
                    )
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            except Exception as e:
                session.rollback()
                raise ValueError(f"Error creating schedule: {str(e)}")
            finally:
                session.close()

        except ValueError as e:
            await interaction.followup.send(
                embed=create_error_embed(title="Invalid Input", description=str(e)),
                ephemeral=True
            )

    async def remove_member_from_schedules(self, session, org_id: int, user_id: str):
        """Remove a member from all active payment schedules in an organization"""
        schedules = session.query(PaymentSchedule)\
            .filter_by(organization_id=org_id)\
            .all()
        
        for schedule in schedules:
            session.query(PaymentScheduleMember)\
                .filter_by(
                    schedule_id=schedule.id,
                    user_id=user_id
                ).delete()

async def setup(bot):
    await bot.add_cog(Organizations(bot))