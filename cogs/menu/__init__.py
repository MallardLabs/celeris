from discord.ext import commands
import discord
from discord import app_commands
from helpers.embed_helpers import create_basic_embed, create_error_embed, create_success_embed
from typing import Optional, List
from models.database import Organization, OrganizationMember, PaymentSchedule, IntervalType, PaymentScheduleMember
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
import asyncio
import helpers.SimplePointsManager as PointsManager
import re
from sqlalchemy import func

class CreateOrgModal(discord.ui.Modal, title="Create Organization"):
    def __init__(self):
        super().__init__()
        self.name = discord.ui.TextInput(
            label="Organization Name",
            placeholder="Enter organization name...",
            min_length=3,
            max_length=32
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate organization name
            org_name = self.name.value.strip()
            
            # Check for invalid characters
            if not re.match(r'^[\w\s-]+$', org_name):
                raise ValueError("Organization name can only contain letters, numbers, spaces, and hyphens.")

            session = interaction.client.db_manager.Session()
            try:
                # Check for existing organization with same name
                existing_org = session.query(Organization)\
                    .filter(func.lower(Organization.name) == func.lower(org_name))\
                    .first()
                
                if existing_org:
                    raise ValueError(f"An organization named '{org_name}' already exists!")

                # Create new organization
                org = Organization(
                    name=org_name,
                    owner_id=str(interaction.user.id),
                    created_at=datetime.utcnow()
                )
                session.add(org)
                session.commit()

                embed = create_success_embed(
                    title="Organization Created",
                    description=(
                        f"Successfully created organization **{org_name}**!\n\n"
                        f"**🏢 Organization ID:** {org.id}\n"
                        f"**👑 Owner:** {interaction.user.mention}\n"
                        f"**📅 Created:** <t:{int(org.created_at.timestamp())}:R>\n\n"
                        "Use `/pay_org` to set up automated payments for this organization."
                    )
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

        except ValueError as e:
            embed = create_error_embed(
                title="Invalid Organization Name",
                description=str(e)
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = create_error_embed(
                title="Error",
                description=f"An error occurred: {str(e)}"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class PaymentScheduleModal(discord.ui.Modal, title="Create Payment Schedule"):
    amount = discord.ui.TextInput(
        label="Amount per Payment",
        placeholder="Enter amount of points (e.g., 1000)",
        required=True,
        min_length=1,
        max_length=10
    )
    
    interval_value = discord.ui.TextInput(
        label="Interval Value",
        placeholder="Enter a number (e.g., 24)",
        required=True,
        min_length=1,
        max_length=5
    )
    
    interval_type = discord.ui.TextInput(
        label="Interval Type",
        placeholder="Use: s (sec), m (min), h (hour), d (day), mm (month)",
        required=True,
        min_length=1,
        max_length=2
    )
    
    total_points = discord.ui.TextInput(
        label="Total Points Pool",
        placeholder="Total points to allocate (e.g., 10000)",
        required=True,
        min_length=1,
        max_length=10
    )

    def __init__(self, org_id: int):
        super().__init__(title="Create Payment Schedule")
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate inputs
            amount = int(self.amount.value)
            interval_value = int(self.interval_value.value)
            interval_type = self.interval_type.value.lower()
            total_points = int(self.total_points.value)

            if amount <= 0 or interval_value <= 0 or total_points <= 0:
                raise ValueError("All numerical values must be positive!")

            valid_intervals = [t.value for t in IntervalType]
            if interval_type not in valid_intervals:
                raise ValueError(
                    f"Interval type must be one of: {', '.join(valid_intervals)}"
                )

            # Convert interval type to human readable for display
            interval_display = {
                's': 'seconds',
                'm': 'minutes',
                'h': 'hours',
                'd': 'days',
                'mm': 'months'
            }[interval_type]

            session = interaction.client.db_manager.Session()
            try:
                # Get organization name and members
                org = session.query(Organization).filter_by(id=self.org_id).first()
                org_name = org.name if org else "Unknown Organization"
                
                # Get current members
                current_members = session.query(OrganizationMember).filter_by(
                    organization_id=self.org_id
                ).all()

                # Create schedule
                schedule = PaymentSchedule(
                    organization_id=self.org_id,
                    amount=amount,
                    interval_value=interval_value,
                    interval_type=IntervalType(interval_type),
                    total_points=total_points,
                    points_paid=0,
                    last_paid_at=datetime.utcnow()  # Ensure this is set
                )
                session.add(schedule)
                session.flush()  # Get the schedule ID

                # Store original members
                if current_members:
                    for member in current_members:
                        schedule_member = PaymentScheduleMember(
                            schedule_id=schedule.id,
                            user_id=member.user_id
                        )
                        session.add(schedule_member)

                # Try initial payment
                initial_payment_info = "\n\n**⚠️ Note:** No members to distribute points to yet."
                if current_members:
                    points_per_member = amount // len(current_members)
                    successful_distributions = 0

                    for member in current_members:
                        try:
                            await interaction.client.points_manager.add_points(
                                user_id=int(member.user_id),
                                amount=points_per_member
                            )
                            successful_distributions += 1
                        except Exception as e:
                            print(f"Error distributing points to {member.user_id}: {e}")

                    if successful_distributions > 0:
                        schedule.points_paid = points_per_member * successful_distributions
                        initial_payment_info = (
                            f"\n\n**📊 Initial Payment**\n"
                            f"• Points per member: {points_per_member:,}\n"
                            f"• Recipients: {successful_distributions}"
                        )

                session.commit()

                # Send response with new embed
                embed = create_success_embed(
                    title="Payment Schedule Created",
                    description=(
                        f"Successfully created a new payment schedule for **{org_name}**!\n\n"
                        f"**💰 Payment Amount:** {amount:,} points\n"
                        f"**⏱️ Interval:** Every {interval_value} {interval_display}\n"
                        f"**🎯 Total Pool:** {total_points:,} points\n"
                        f"**📊 Total Payments:** {total_points // amount}"
                        f"{initial_payment_info}"
                    )
                )
                
                try:
                    await interaction.response.send_message(embed=embed)
                except discord.errors.NotFound:
                    # If interaction expired, try to send a follow-up
                    await interaction.followup.send(embed=embed)
                
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

        except ValueError as e:
            try:
                await interaction.response.send_message(
                    embed=create_error_embed(title="Invalid Input", description=str(e)),
                    ephemeral=True
                )
            except discord.errors.NotFound:
                await interaction.followup.send(
                    embed=create_error_embed(title="Invalid Input", description=str(e)),
                    ephemeral=True
                )
        except Exception as e:
            try:
                await interaction.response.send_message(
                    embed=create_error_embed(title="Error", description=f"An error occurred: {str(e)}"),
                    ephemeral=True
                )
            except discord.errors.NotFound:
                await interaction.followup.send(
                    embed=create_error_embed(title="Error", description=f"An error occurred: {str(e)}"),
                    ephemeral=True
                )

class PaymentScheduleView(discord.ui.View):
    def create_progress_bar(self, current: int, total: int, width: int = 10) -> str:
        filled = '█'
        empty = '░'
        progress = current / total
        filled_amount = round(width * progress)
        empty_amount = width - filled_amount
        percentage = progress * 100
        return f"{filled * filled_amount}{empty * empty_amount} {percentage:.1f}%"

    def __init__(self, org_id: int, org_name: str):
        super().__init__()
        self.org_id = org_id
        self.org_name = org_name

    @discord.ui.button(label="Create Schedule", style=discord.ButtonStyle.green, emoji="📅")
    async def create_schedule(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PaymentScheduleModal(self.org_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="View Schedules", style=discord.ButtonStyle.blurple, emoji="📊")
    async def view_schedules(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = interaction.client.db_manager.Session()
        try:
            schedules = session.query(PaymentSchedule).filter_by(organization_id=self.org_id).all()
            
            if not schedules:
                embed = create_basic_embed(
                    title=f"{self.org_name} • Payment Schedules",
                    description=(
                        "### No Active Schedules\n"
                        "Time to set up your first payment schedule!\n\n"
                        "**💡 Benefits of Payment Schedules**\n"
                        "• Automate regular payments\n"
                        "• Ensure timely distributions\n"
                        "• Track payment history\n\n"
                        "**🚀 Getting Started**\n"
                        "Click 'Create Schedule' to set up your first automated payment!"
                    )
                )
            else:
                embed = create_basic_embed(
                    title=f"{self.org_name} • Payment Schedules",
                    description=(
                        "### Active Payment Schedules\n"
                        f"Managing {len(schedules)} payment schedule{'s' if len(schedules) != 1 else ''}.\n\n"
                        "**📊 Schedule Details**"
                    )
                )
                
                # Map short interval types to display names
                interval_display = {
                    's': 'seconds',
                    'm': 'minutes',
                    'h': 'hours',
                    'd': 'days',
                    'mm': 'months'
                }
                
                for schedule in schedules:
                    points_paid = schedule.points_paid or 0
                    remaining_points = schedule.total_points - points_paid
                    remaining_payments = remaining_points // schedule.amount
                    
                    # Get human-readable interval type
                    interval_type = schedule.interval_type.value
                    interval_name = interval_display[interval_type]
                    
                    # Create progress bar
                    progress_bar = self.create_progress_bar(points_paid, schedule.total_points, width=15)
                    
                    embed.add_field(
                        name=f"Schedule #{schedule.id}",
                        value=(
                            f"💰 **Amount:** {schedule.amount:,} points\n"
                            f"⏱️ **Interval:** {schedule.interval_value} {interval_name}\n"
                            f"📈 **Progress:**\n"
                            f"`{progress_bar}`\n"
                            f"**Points Distributed:** {points_paid:,} / {schedule.total_points:,}\n"
                            f"🎯 **Remaining Payments:** {remaining_payments}\n"
                            f"💫 **Payment Rate:** {schedule.amount:,} points per {schedule.interval_value} {interval_name}"
                        ),
                        inline=False
                    )

            await interaction.response.edit_message(embed=embed, view=self)
        finally:
            session.close()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey, emoji="⬅️")
    async def back_to_org(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = OrganizationManageView(self.org_id, self.org_name)
        embed = create_basic_embed(
            title=f"{self.org_name} • Dashboard",
            description=(
                "### Organization Dashboard\n"
                "Manage your organization with powerful tools.\n\n"
                "**🎯 Available Actions**\n"
                "• View and manage members\n"
                "• Set up payment schedules\n"
                "• Monitor organization activity\n\n"
                "**💡 Quick Tip**\n"
                "Regular updates keep your organization running smoothly!"
            )
        )
        await interaction.response.edit_message(embed=embed, view=view)

class OrganizationManageView(discord.ui.View):
    def __init__(self, org_id: int, org_name: str):
        super().__init__()
        self.org_id = org_id
        self.org_name = org_name

    @discord.ui.button(label="Members", style=discord.ButtonStyle.blurple, emoji="👥")
    async def view_members(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = interaction.client.db_manager.Session()
        try:
            org = session.query(Organization).filter_by(id=self.org_id).first()
            members = session.query(OrganizationMember).filter_by(organization_id=self.org_id).all()
            
            embed = create_basic_embed(
                title=f"{self.org_name} • Members",
                description=(
                    "### Organization Members\n"
                    f"Manage your team of {len(members)} members.\n\n"
                    f"**👑 Owner**\n<@{org.owner_id}>\n\n"
                    "**🔧 Member Management**\n"
                    "`/add_member` Add new members to your organization\n"
                    "`/remove_member` Remove existing members\n\n"
                    "**💡 Quick Tips**\n"
                    "• Members can receive automated payments\n"
                    "• Members can view organization statistics\n"
                    "• Only owners can manage members"
                )
            )

            if members:
                formatted_members = []
                for member in members:
                    formatted_members.append(f"• <@{member.user_id}>")
                
                if len(formatted_members) > 0:
                    embed.add_field(
                        name="👥 Current Members",
                        value="\n".join(formatted_members),
                        inline=False
                    )
            else:
                embed.add_field(
                    name="👥 Current Members",
                    value="No members yet. Add some using `/add_member`!",
                    inline=False
                )
            
            await interaction.response.edit_message(embed=embed, view=self)
        finally:
            session.close()

    @discord.ui.button(label="Payment Center", style=discord.ButtonStyle.blurple, emoji="💰")
    async def manage_schedules(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = create_basic_embed(
            title=f"{self.org_name} • Payment Center",
            description=(
                "### Automated Payment System\n"
                "Streamline your organization's payment process.\n\n"
                "**🎯 Available Actions**\n"
                "• Create new payment schedules\n"
                "• View and manage existing schedules\n"
                "• Monitor payment history\n\n"
                "**💡 Quick Tips**\n"
                "• Set up recurring payments\n"
                "• Choose flexible intervals\n"
                "• Track payment statistics"
            )
        )
        view = PaymentScheduleView(self.org_id, self.org_name)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey, emoji="⬅️")
    async def back_to_orgs(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenuView()
        embed = create_basic_embed(
            title="Organization Hub",
            description=(
                "### Welcome to Your Organization Hub\n"
                "Manage your organizations with powerful tools.\n\n"
                "**🔧 Management Tools**\n"
                "• `/add_member` Add members to your organization\n"
                "• `/remove_member` Remove members\n"
                "• View member statistics\n"
                "• Manage payment schedules\n\n"
                "**💡 Quick Tips**\n"
                "• Create multiple organizations\n"
                "• Set up automated payments\n"
                "• Monitor organization growth"
            )
        )
        await interaction.response.edit_message(embed=embed, view=view)

class MainMenuView(discord.ui.View):
    @discord.ui.button(label="New Organization", style=discord.ButtonStyle.green, emoji="✨")
    async def create_org(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = create_basic_embed(
            title="Create Your Organization",
            description=(
                "### Let's Build Something Great\n"
                "Create a new organization in seconds.\n\n"
                "**✨ Organization Features**\n"
                " Automated payment systems\n"
                "• Member management\n"
                "• Performance tracking\n"
                "• Customizable settings\n\n"
                "**📋 Requirements**\n"
                "• Name: 3-32 characters\n"
                "• Must be unique\n"
                "• No special characters\n\n"
                "**💡 Quick Tip**\n"
                "Choose a memorable name that reflects your organization's purpose!"
            )
        )
        await interaction.response.send_modal(CreateOrgModal())

    @discord.ui.button(label="My Organizations", style=discord.ButtonStyle.blurple, emoji="🏢")
    async def view_orgs(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = interaction.client.db_manager.Session()
        try:
            orgs = session.query(Organization).filter_by(owner_id=str(interaction.user.id)).all()
            
            if not orgs:
                embed = create_basic_embed(
                    title="My Organizations",
                    description=(
                        "### No Organizations Yet\n"
                        "Time to create your first organization!\n\n"
                        "**✨ Why Create an Organization?**\n"
                        "• Automate member payments\n"
                        "• Track performance metrics\n"
                        "• Manage team members\n"
                        "• Streamline operations\n\n"
                        "**🚀 Getting Started**\n"
                        "Click the 'New Organization' button to begin your journey!"
                    )
                )
                await interaction.response.edit_message(embed=embed, view=self)
                return

            embed = create_basic_embed(
                title="My Organizations",
                description=(
                    "### Your Organization Portfolio\n"
                    f"Managing {len(orgs)} organization{'s' if len(orgs) != 1 else ''}.\n\n"
                    "**🎯 Quick Actions**\n"
                    "• Select an organization to manage\n"
                    "• View member lists\n"
                    "• Manage payment schedules\n\n"
                    "**💡 Quick Tip**\n"
                    "Keep your organizations organized by using clear, distinctive names!"
                )
            )

            view = discord.ui.View()
            for org in orgs:
                org_button = discord.ui.Button(
                    label=org.name,
                    style=discord.ButtonStyle.secondary,
                    emoji="🏢"
                )
                
                async def make_callback(org_id: int, org_name: str):
                    async def callback(interaction: discord.Interaction):
                        view = OrganizationManageView(org_id, org_name)
                        embed = create_basic_embed(
                            title=f"{org_name} • Dashboard",
                            description=(
                                "### Organization Dashboard\n"
                                "Manage your organization with powerful tools.\n\n"
                                "**🎯 Available Actions**\n"
                                "• View and manage members\n"
                                "• Set up payment schedules\n"
                                "• Monitor organization activity\n\n"
                                "**💡 Quick Tip**\n"
                                "Regular updates keep your organization running smoothly!"
                            )
                        )
                        await interaction.response.edit_message(embed=embed, view=view)
                    return callback
                
                org_button.callback = await make_callback(org.id, org.name)
                view.add_item(org_button)

            # Add back button
            back_button = discord.ui.Button(
                label="Back",
                style=discord.ButtonStyle.grey,
                emoji="⬅️"
            )
            
            async def back_callback(interaction: discord.Interaction):
                embed = create_basic_embed(
                    title="Organization Hub",
                    description=(
                        "### Welcome Back!\n"
                        "Your organization management center.\n\n"
                        "**🎯 Quick Actions**\n"
                        " Create new organizations\n"
                        "• Manage existing ones\n"
                        "• Set up payment systems\n\n"
                        "**💡 Quick Tip**\n"
                        "Regular check-ins help maintain smooth operations!"
                    )
                )
                await interaction.response.edit_message(embed=embed, view=MainMenuView())
            
            back_button.callback = back_callback
            view.add_item(back_button)

            await interaction.response.edit_message(embed=embed, view=view)
        finally:
            session.close()

    @discord.ui.button(label="Active Schedules", style=discord.ButtonStyle.success, emoji="⏱️", row=0)
    async def view_schedules(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ActiveSchedulesView()
        embed = await view.display_initial_page(interaction)
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])

class Menu(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.payment_task = self.bot.loop.create_task(self.process_payments())
        self.last_payment_time = {}

    async def process_payments(self):
        """Process scheduled payments"""
        print("Payment processor initialized")
        await self.bot.wait_until_ready()
        self.is_processing = True
        
        while not self.bot.is_closed() and self.is_processing:
            try:
                session = self.bot.db_manager.Session()
                try:
                    # Get all active schedules
                    schedules = session.query(PaymentSchedule)\
                        .filter(PaymentSchedule.points_paid < PaymentSchedule.total_points)\
                        .all()
                    
                    current_time = datetime.utcnow()
                    
                    # Check for second-based schedules
                    has_second_intervals = any(
                        schedule.interval_type.value == 's' 
                        for schedule in schedules 
                        if schedule.points_paid < schedule.total_points
                    )

                    for schedule in schedules:
                        try:
                            if not schedule.last_paid_at:
                                schedule.last_paid_at = current_time
                                session.commit()
                                continue

                            interval_type = schedule.interval_type.value
                            interval_value = schedule.interval_value
                            last_paid = schedule.last_paid_at

                            # Calculate time until next payment
                            if interval_type == 'mm':  # Monthly
                                months_diff = (current_time.year - last_paid.year) * 12 + (current_time.month - last_paid.month)
                                should_pay = months_diff >= interval_value
                            else:
                                seconds_map = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
                                interval_seconds = interval_value * seconds_map[interval_type]
                                time_diff = (current_time - last_paid).total_seconds()
                                should_pay = time_diff >= interval_seconds

                            if should_pay:
                                remaining_points = schedule.total_points - schedule.points_paid
                                if remaining_points <= 0:
                                    continue

                                payment_amount = min(schedule.amount, remaining_points)

                                # Process payment
                                if schedule.user_id:  # Individual payment
                                    try:
                                        user_id = int(schedule.user_id)
                                        await self.bot.points_manager.add_points(
                                            user_id=user_id,
                                            amount=payment_amount
                                        )
                                        
                                        # Update immediately after successful payment
                                        schedule.points_paid += payment_amount
                                        schedule.last_paid_at = current_time
                                        session.commit()

                                        # Send enhanced DM notification
                                        await self.send_payment_notification(
                                            user_id=user_id,
                                            schedule=schedule,
                                            payment_amount=payment_amount,
                                            session=session
                                        )

                                    except Exception as e:
                                        print(f"Error processing individual payment: {e}")
                                        continue

                        except Exception as e:
                            print(f"Error processing schedule #{schedule.id}: {e}")
                            continue

                finally:
                    session.close()

            except Exception as e:
                print(f"Error in payment processing main loop: {e}")

            # Adjust sleep time based on schedule types
            if has_second_intervals:
                await asyncio.sleep(0.1)  # Check every 100ms for second-based intervals
            else:
                await asyncio.sleep(1)  # Check every second for longer intervals

    async def send_payment_notification(self, user_id: int, schedule: PaymentSchedule, payment_amount: int, session, is_initial: bool = False):
        """Send a detailed DM notification for a payment"""
        try:
            user = await self.bot.fetch_user(user_id)
            if not user:
                return

            # Get sender information
            sender = await self.bot.fetch_user(int(schedule.created_by))
            sender_name = sender.name if sender else "Unknown"

            # Calculate next payment time
            interval_type = schedule.interval_type.value
            interval_value = schedule.interval_value
            
            interval_display = {
                's': 'seconds',
                'm': 'minutes',
                'h': 'hours',
                'd': 'days',
                'mm': 'months'
            }[interval_type]

            # Format progress bar (10 segments)
            progress = schedule.points_paid / schedule.total_points
            progress_bar = "█" * int(progress * 10) + "░" * (10 - int(progress * 10))
            progress_percentage = progress * 100

            if schedule.organization_id:
                # Organization payment
                org = session.query(Organization).filter_by(id=schedule.organization_id).first()
                org_name = org.name if org else "Unknown Organization"
                
                title = "First Organization Payment" if is_initial else "Organization Payment Received"
                embed = create_basic_embed(
                    title=title,
                    description=(
                        f"### Payment from {org_name}\n"
                        f"{'Initial payment received!' if is_initial else 'You\'ve received a scheduled payment!'}\n\n"
                        f"**💰 Amount Received**\n"
                        f"`{payment_amount:,}` points\n\n"
                        f"**📊 Schedule Progress**\n"
                        f"`{progress_bar}` {progress_percentage:.1f}%\n"
                        f"(`{schedule.points_paid:,}`/`{schedule.total_points:,}` points)\n\n"
                        f"**⏱️ Payment Details**\n"
                        f"• Frequency: Every {interval_value} {interval_display}\n"
                        f"• Created by: {sender_name}\n"
                        f"• Schedule ID: #{schedule.id}"
                    )
                )
                embed.set_footer(text=f"🏢 {org_name} • {'Initial Payment' if is_initial else 'Automated Payment'}")
                
            else:
                # Individual payment
                title = "First Payment Received" if is_initial else "Payment Received"
                embed = create_basic_embed(
                    title=title,
                    description=(
                        f"### Individual Payment\n"
                        f"{'Initial payment received!' if is_initial else 'You\'ve received a scheduled payment!'}\n\n"
                        f"**💰 Amount Received**\n"
                        f"`{payment_amount:,}` points\n\n"
                        f"**📊 Schedule Progress**\n"
                        f"`{progress_bar}` {progress_percentage:.1f}%\n"
                        f"(`{schedule.points_paid:,}`/`{schedule.total_points:,}` points)\n\n"
                        f"**⏱️ Payment Details**\n"
                        f"• Frequency: Every {interval_value} {interval_display}\n"
                        f"• Sent by: {sender_name}\n"
                        f"• Schedule ID: #{schedule.id}"
                    )
                )
                embed.set_footer(text=f"👤 Individual Payment • {'Initial Payment' if is_initial else 'Automated Payment'}")

            # Add timestamp
            embed.timestamp = datetime.utcnow()

            await user.send(embed=embed)
            
        except Exception as e:
            print(f"Failed to send DM to user {user_id}: {e}")

    @app_commands.command(name="start", description="Start using Celeris")
    async def start(self, interaction: discord.Interaction):
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
        
        # Add the banner image
        embed.set_image(url="attachment://celerisa.png")
        
        # Add footer
        embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
        
        view = StartView()
        await interaction.response.send_message(
            file=discord.File("celerisa.png"),
            embed=embed,
            view=view
        )

    @app_commands.command(
        name="pay_user",
        description="Create an automated payment schedule for a user"
    )
    @app_commands.describe(
        user="The user to send payments to",
        amount="Amount of points per payment",
        interval_value="How often to make payments (e.g., 24)",
        interval_type="Time unit for interval (s/m/h/d/mm)",
        total_points="Total points to distribute over time"
    )
    async def pay_user(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: int,
        interval_value: int,
        interval_type: str,
        total_points: int
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)

            # Validate inputs
            if amount <= 0 or interval_value <= 0 or total_points <= 0:
                raise ValueError("All numerical values must be positive!")

            interval_type = interval_type.lower()
            valid_intervals = [t.value for t in IntervalType]
            if interval_type not in valid_intervals:
                raise ValueError(f"Invalid interval type! Use: {', '.join(valid_intervals)}")

            if total_points < amount:
                raise ValueError("Total points must be greater than or equal to amount per payment!")

            session = interaction.client.db_manager.Session()
            try:
                schedule = PaymentSchedule(
                    user_id=str(user.id),
                    amount=amount,
                    interval_value=interval_value,
                    interval_type=IntervalType(interval_type),
                    total_points=total_points,
                    points_paid=0,
                    created_by=str(interaction.user.id),
                    created_at=datetime.utcnow(),
                    last_paid_at=datetime.utcnow()
                )
                session.add(schedule)
                session.flush()  # Get the schedule ID
                
                # Make initial payment
                try:
                    await self.bot.points_manager.add_points(
                        user_id=user.id,
                        amount=amount
                    )
                    schedule.points_paid = amount
                    schedule.last_paid_at = datetime.utcnow()
                    
                    # Send initial payment notification
                    await self.send_payment_notification(
                        user_id=user.id,
                        schedule=schedule,
                        payment_amount=amount,
                        session=session,
                        is_initial=True
                    )
                    
                    initial_payment_info = (
                        f"\n\n**📊 Initial Payment**\n"
                        f"• Points sent: {amount:,}\n"
                        f"• Recipient: {user.mention}"
                    )
                except Exception as e:
                    print(f"Error in initial payment: {e}")
                    initial_payment_info = "\n\n**⚠️ Note:** Initial payment failed"

                session.commit()

                # Format interval type for display
                interval_display = {
                    's': 'seconds',
                    'm': 'minutes',
                    'h': 'hours',
                    'd': 'days',
                    'mm': 'months'
                }[interval_type]

                embed = create_success_embed(
                    title="Individual Payment Schedule Created",
                    description=(
                        "### Schedule Details\n"
                        f"Successfully created a new payment schedule!\n\n"
                        f"**👤 Recipient:** {user.mention}\n"
                        f"**💰 Payment Amount:** {amount:,} points\n"
                        f"**⏱️ Interval:** Every {interval_value} {interval_display}\n"
                        f"**🎯 Total Pool:** {total_points:,} points\n"
                        f"**📊 Total Payments:** {total_points // amount}"
                        f"{initial_payment_info}"
                    )
                )
                
                # Use followup since we deferred earlier
                await interaction.followup.send(embed=embed, ephemeral=True)

            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

        except ValueError as e:
            await interaction.followup.send(
                embed=create_error_embed(title="Invalid Input", description=str(e)),
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                embed=create_error_embed(title="Error", description=f"An error occurred: {str(e)}"),
                ephemeral=True
            )

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
        # ... (rest of the organization payment logic)

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

class StartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Organizations", style=discord.ButtonStyle.primary, emoji="🏢", row=0)
    async def manage_orgs(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = create_basic_embed(
            title="Organization Management",
            description=(
                "### Manage Your Organizations\n"
                "Create and manage your organizations here.\n\n"
                "**💡 Quick Actions**\n"
                "• Create a new organization\n"
                "• View existing organizations\n"
                "• Manage members and settings\n\n"
                "**📝 Payment Commands**\n"
                "• `/pay_org` - Set up automated payments for an organization\n"
                "• `/pay_user` - Set up automated payments for a user"
            )
        )
        embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
        view = OrganizationManagementView()
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])

    @discord.ui.button(label="Payment History", style=discord.ButtonStyle.secondary, emoji="📜", row=0)
    async def payment_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = PaymentHistoryView()
        embed = await view.display_initial_page(interaction)
        embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])

    @discord.ui.button(label="Active Schedules", style=discord.ButtonStyle.success, emoji="⏱️", row=0)
    async def view_schedules(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ActiveSchedulesView()
        embed = await view.display_initial_page(interaction)
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])

class PaymentHistoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.current_page = 0
        self.items_per_page = 5

    async def display_initial_page(self, interaction: discord.Interaction):
        session = interaction.client.db_manager.Session()
        try:
            total_schedules = session.query(PaymentSchedule).count()
            total_pages = (total_schedules - 1) // self.items_per_page + 1

            schedules = session.query(PaymentSchedule)\
                .order_by(PaymentSchedule.created_at.desc())\
                .offset(self.current_page * self.items_per_page)\
                .limit(self.items_per_page)\
                .all()

            embed = create_basic_embed(
                title="Payment Schedules",
                description=f"Page {self.current_page + 1} of {total_pages}"
            )

            if not schedules:
                embed.description = "No payment schedules found."
            else:
                for schedule in schedules:
                    # Calculate progress
                    progress = schedule.points_paid / schedule.total_points
                    progress_bar = "█" * int(progress * 10) + "░" * (10 - int(progress * 10))
                    progress_percentage = progress * 100

                    # Get target information
                    if schedule.organization_id:
                        org = session.query(Organization).filter_by(id=schedule.organization_id).first()
                        target_name = f"🏢 {org.name}" if org else "Unknown Organization"
                    else:
                        user = await interaction.client.fetch_user(int(schedule.user_id))
                        target_name = f"👤 {user.name}" if user else "Unknown User"

                    # Get creator information
                    creator = await interaction.client.fetch_user(int(schedule.created_by))
                    creator_name = creator.name if creator else "Unknown"

                    # Format interval
                    interval_display = {
                        's': 'seconds',
                        'm': 'minutes',
                        'h': 'hours',
                        'd': 'days',
                        'mm': 'months'
                    }[schedule.interval_type.value]

                    embed.add_field(
                        name=f"Schedule #{schedule.id}",
                        value=(
                            f"**Target:** {target_name}\n"
                            f"**💰 Amount:** {schedule.amount:,} points\n"
                            f"**️ Interval:** Every {schedule.interval_value} {interval_display}\n"
                            f"**📊 Progress:**\n"
                            f"`{progress_bar}` {progress_percentage:.1f}%\n"
                            f"(`{schedule.points_paid:,}`/`{schedule.total_points:,}` points)\n"
                            f"**👤 Created by:** {creator_name}\n"
                            f"**📅 Created:** <t:{int(schedule.created_at.timestamp())}:R>"
                        ),
                        inline=False
                    )

            self.children[0].disabled = self.current_page == 0
            self.children[1].disabled = self.current_page >= total_pages - 1

            return embed
        finally:
            session.close()

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(0, self.current_page - 1)
        embed = await self.display_initial_page(interaction)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        embed = await self.display_initial_page(interaction)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, emoji="🏠")
    async def back_to_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = create_basic_embed(
            title="Welcome to Celeris",
            description="Welcome back to the main menu!",
            add_footer=True
        )
        view = StartView()
        await interaction.response.edit_message(embed=embed, view=view)

class OrganizationManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Create Organization", style=discord.ButtonStyle.primary, emoji="🏢", row=0)
    async def create_org(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CreateOrgModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="View Organizations", style=discord.ButtonStyle.secondary, emoji="📋", row=0)
    async def view_orgs(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = interaction.client.db_manager.Session()
        try:
            orgs = session.query(Organization).all()
            if not orgs:
                embed = create_basic_embed(
                    title="No Organizations Found",
                    description="You haven't created any organizations yet. Click 'Create Organization' to get started!"
                )
                await interaction.response.edit_message(embed=embed, view=self)
                return

            embed = create_basic_embed(
                title="Your Organizations",
                description="Here are your organizations:"
            )
            
            for org in orgs:
                member_count = session.query(OrganizationMember).filter_by(organization_id=org.id).count()
                embed.add_field(
                    name=f"{org.name} (ID: {org.id})",
                    value=(
                        f"**👥 Members:** {member_count}\n"
                        f"**👑 Owner:** <@{org.owner_id}>"
                    ),
                    inline=False
                )

            await interaction.response.edit_message(embed=embed, view=self)
        finally:
            session.close()

    @discord.ui.button(label="Back to Main", style=discord.ButtonStyle.danger, emoji="🏠", row=1)
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
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])

class ActiveSchedulesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.current_page = 0
        self.items_per_page = 5

    async def display_initial_page(self, interaction: discord.Interaction):
        session = interaction.client.db_manager.Session()
        try:
            # Only get active schedules (not completed)
            schedules = session.query(PaymentSchedule)\
                .filter(PaymentSchedule.points_paid < PaymentSchedule.total_points)\
                .order_by(PaymentSchedule.created_at.desc())\
                .all()

            embed = create_basic_embed(
                title="Active Payment Schedules",
                description="Currently running payment schedules"
            )

            if not schedules:
                embed.description = "No active payment schedules found."
            else:
                for schedule in schedules:
                    # ... similar to PaymentHistoryView formatting ...
                    progress = schedule.points_paid / schedule.total_points
                    progress_bar = "█" * int(progress * 10) + "░" * (10 - int(progress * 10))
                    progress_percent = f"{progress * 100:.1f}%"
                    
                    embed.add_field(
                        name=f"Schedule #{schedule.id}",
                        value=(
                            f"**Progress:** {progress_bar} {progress_percent}\n"
                            f"**Points Paid:** {schedule.points_paid:,}/{schedule.total_points:,}\n"
                            f"**Frequency:** Every {schedule.frequency_days} days\n"
                            f"**Next Payment:** <t:{int(schedule.next_payment_date.timestamp())}:R>\n"
                            f"**Created:** <t:{int(schedule.created_at.timestamp())}:R>"
                        ),
                        inline=False
                    )
            embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
            return embed
        finally:
            session.close()

    # Add navigation buttons similar to PaymentHistoryView

class OrganizationDetailView(discord.ui.View):
    def __init__(self, org_id: int):
        super().__init__(timeout=180)
        self.org_id = org_id

    @discord.ui.button(label="Transfer Ownership", style=discord.ButtonStyle.primary, emoji="👑")
    async def transfer_ownership(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TransferOwnershipModal(self.org_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Delete Organization", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_org(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = interaction.client.db_manager.Session()
        try:
            org = session.query(Organization).filter_by(id=self.org_id).first()
            if not org:
                await interaction.response.send_message("Organization not found!", ephemeral=True)
                return

            if str(interaction.user.id) != org.owner_id:
                await interaction.response.send_message("You don't have permission to delete this organization!", ephemeral=True)
                return

            # Create confirmation button
            confirm_view = ConfirmationView()
            embed = create_basic_embed(
                title="⚠️ Confirm Deletion",
                description=f"Are you sure you want to delete **{org.name}**?\nThis action cannot be undone!"
            )
            await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)

            # Wait for confirmation
            await confirm_view.wait()
            if confirm_view.value:
                # Delete all related records
                session.query(PaymentScheduleMember).filter(
                    PaymentScheduleMember.schedule_id.in_(
                        session.query(PaymentSchedule.id).filter_by(organization_id=self.org_id)
                    )
                ).delete(synchronize_session=False)
                session.query(PaymentSchedule).filter_by(organization_id=self.org_id).delete()
                session.query(OrganizationMember).filter_by(organization_id=self.org_id).delete()
                session.delete(org)
                session.commit()
                
                success_embed = create_success_embed(
                    title="Organization Deleted",
                    description=f"Successfully deleted organization **{org.name}**"
                )
                await interaction.edit_original_message(embed=success_embed, view=None)
            else:
                await interaction.delete_original_message()

        except Exception as e:
            session.rollback()
            await interaction.followup.send(f"Error deleting organization: {str(e)}", ephemeral=True)
        finally:
            session.close()

class TransferOwnershipModal(discord.ui.Modal, title="Transfer Ownership"):
    def __init__(self, org_id: int):
        super().__init__()
        self.org_id = org_id
        self.new_owner = discord.ui.TextInput(
            label="New Owner ID",
            placeholder="Enter the Discord ID of the new owner",
            min_length=17,
            max_length=20
        )
        self.add_item(self.new_owner)

    async def on_submit(self, interaction: discord.Interaction):
        session = interaction.client.db_manager.Session()
        try:
            org = session.query(Organization).filter_by(id=self.org_id).first()
            if not org:
                raise ValueError("Organization not found!")

            if str(interaction.user.id) != org.owner_id:
                raise ValueError("You don't have permission to transfer ownership!")

            new_owner_id = self.new_owner.value.strip()
            try:
                new_owner = await interaction.client.fetch_user(int(new_owner_id))
            except:
                raise ValueError("Invalid user ID!")

            org.owner_id = str(new_owner.id)
            session.commit()

            embed = create_success_embed(
                title="Ownership Transferred",
                description=f"Successfully transferred ownership of **{org.name}** to {new_owner.mention}"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
        except Exception as e:
            session.rollback()
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
        finally:
            session.close()

class ViewOrganizationsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.current_page = 0
        self.items_per_page = 5
        self.advanced_view = False
        self.selected_org_id = None
        self.viewing_members = False
        self.member_page = 0
        self.members_per_page = 15

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.viewing_members:
            self.member_page = max(0, self.member_page - 1)
        else:
            self.current_page = max(0, self.current_page - 1)
        await self.update_view(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.viewing_members:
            self.member_page += 1
        else:
            self.current_page += 1
        await self.update_view(interaction)

    @discord.ui.button(label="Toggle Details", style=discord.ButtonStyle.primary, emoji="🔍")
    async def toggle_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.advanced_view = not self.advanced_view
        self.viewing_members = False
        self.member_page = 0
        button.label = "Simple View" if self.advanced_view else "Detailed View"
        await self.update_view(interaction)

    @discord.ui.button(label="View Members", style=discord.ButtonStyle.success, emoji="👥")
    async def view_members(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_org_id:
            self.viewing_members = not self.viewing_members
            self.member_page = 0
            button.label = "Back to Org" if self.viewing_members else "View Members"
            await self.update_view(interaction)
        else:
            await interaction.response.send_message("Please select an organization first!", ephemeral=True)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, emoji="🏠", row=1)
    async def back_to_org_hub(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = create_basic_embed(
            title="Organization Management",
            description=(
                "### Manage Your Organizations\n"
                "Create and manage your organizations here.\n\n"
                "**💡 Quick Actions**\n"
                "• Create a new organization\n"
                "• View existing organizations\n"
                "• Manage members and settings\n\n"
                "**📝 Payment Commands**\n"
                "• `/pay_org` - Set up automated payments for an organization\n"
                "• `/pay_user` - Set up automated payments for a user"
            )
        )
        embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
        view = OrganizationManagementView()
        await interaction.response.edit_message(embed=embed, view=view)

    async def update_view(self, interaction: discord.Interaction):
        session = interaction.client.db_manager.Session()
        try:
            if self.viewing_members and self.selected_org_id:
                await self.show_member_list(interaction, session)
            else:
                await self.show_organization_list(interaction, session)
        finally:
            session.close()

    async def show_member_list(self, interaction: discord.Interaction, session):
        org = session.query(Organization).filter_by(id=self.selected_org_id).first()
        if not org:
            await interaction.response.send_message("Organization not found!", ephemeral=True)
            return

        members = session.query(OrganizationMember).filter_by(organization_id=org.id).all()
        total_members = len(members)
        total_pages = (total_members - 1) // self.members_per_page + 1

        start_idx = self.member_page * self.members_per_page
        end_idx = start_idx + self.members_per_page
        current_members = members[start_idx:end_idx]

        embed = create_basic_embed(
            title=f"Members of {org.name}",
            description=(
                f"**Total Members:** {total_members}\n"
                f"**Page:** {self.member_page + 1} of {total_pages}\n\n"
                "### Member List\n"
            )
        )

        member_list = []
        for idx, member in enumerate(current_members, start=start_idx + 1):
            try:
                user = await interaction.client.fetch_user(int(member.user_id))
                join_date = member.joined_at.strftime("%Y-%m-%d")
                member_list.append(f"`{idx}.` {user.name} (Joined: {join_date})")
            except:
                member_list.append(f"`{idx}.` Unknown User ({member.user_id})")

        if member_list:
            embed.description += "\n".join(member_list)
        else:
            embed.description += "\n*No members found*"

        # Update button states
        self.children[0].disabled = self.member_page == 0  # Previous
        self.children[1].disabled = self.member_page >= total_pages - 1  # Next

        embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
        await interaction.response.edit_message(embed=embed, view=self)

    async def show_organization_list(self, interaction: discord.Interaction, session):
        total_orgs = session.query(Organization).count()
        total_pages = (total_orgs - 1) // self.items_per_page + 1

        orgs = session.query(Organization)\
            .order_by(Organization.created_at.desc())\
            .offset(self.current_page * self.items_per_page)\
            .limit(self.items_per_page)\
            .all()

        embed = create_basic_embed(
            title="Organizations",
            description=f"Page {self.current_page + 1} of {total_pages}\n" +
                       ("**🔍 Detailed View**" if self.advanced_view else "**📑 Simple View**")
        )

        if not orgs:
            embed.description = "No organizations found."
            self.selected_org_id = None
        else:
            for org in orgs:
                owner = await interaction.client.fetch_user(int(org.owner_id))
                owner_name = owner.name if owner else "Unknown"

                members = session.query(OrganizationMember).filter_by(organization_id=org.id).all()
                member_count = len(members)

                active_schedules = session.query(PaymentSchedule)\
                    .filter_by(organization_id=org.id)\
                    .filter(PaymentSchedule.points_paid < PaymentSchedule.total_points)\
                    .count()

                if self.advanced_view:
                    embed.add_field(
                        name=f"🏢 {org.name}",
                        value=(
                            f"**👑 Owner:** {owner_name}\n"
                            f"**📊 Stats**\n"
                            f"• Members: {member_count}\n"
                            f"• Active Schedules: {active_schedules}\n"
                            f"• Created: <t:{int(org.created_at.timestamp())}:R>\n"
                            f"\n**🔧 Management**\n"
                            f"Use `/pay_org {org.name}` to create payment schedule\n"
                            f"Organization ID: `{org.id}`\n"
                            f"\nClick 'View Members' to see the full member list"
                        ),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"🏢 {org.name}",
                        value=(
                            f"**👑 Owner:** {owner_name}\n"
                            f"**👥 Members:** {member_count}\n"
                            f"**⏱️ Active Schedules:** {active_schedules}\n"
                            f"**📅 Created:** <t:{int(org.created_at.timestamp())}:R>"
                        ),
                        inline=False
                    )

            # Store the last viewed org ID for member view
            if orgs:
                self.selected_org_id = orgs[0].id

        # Update button states
        self.children[0].disabled = self.current_page == 0  # Previous
        self.children[1].disabled = self.current_page >= total_pages - 1  # Next

        embed.set_footer(text="☁   Celeris runs securely on Mallard Cloud")
        await interaction.response.edit_message(embed=embed, view=self)

async def setup(bot: commands.Bot):
    await bot.add_cog(Menu(bot)) 
