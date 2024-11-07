from discord.ext import commands
import discord
from discord import app_commands
from helpers.embed_helpers import create_basic_embed, create_error_embed, create_success_embed
from typing import Optional, List
from models.database import Organization, OrganizationMember, PaymentSchedule, IntervalType
from sqlalchemy import select
from datetime import datetime, timedelta
import asyncio
import helpers.SimplePointsManager as PointsManager

class CreateOrgModal(discord.ui.Modal, title="Create Organization"):
    name = discord.ui.TextInput(
        label="Organization Name",
        placeholder="Enter organization name",
        required=True,
        min_length=3,
        max_length=32
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            session = interaction.client.db_manager.Session()
            try:
                org = Organization(
                    name=self.name.value,
                    owner_id=str(interaction.user.id)
                )
                session.add(org)
                session.commit()
                
                embed = create_success_embed(
                    title="Organization Created",
                    description=(
                        "### Success!\n"
                        f"Organization **{self.name.value}** has been created.\n\n"
                        "**🎯 Next Steps**\n"
                        "• Add members using `/add_member`\n"
                        "• Set up payment schedules\n"
                        "• Start managing your organization\n\n"
                        "**💡 Quick Tip**\n"
                        "Regular updates keep your organization running smoothly!"
                    )
                )
                view = MainMenuView()
                await interaction.response.edit_message(embed=embed, view=view)
            finally:
                session.close()
        except Exception as e:
            await interaction.response.send_message(
                embed=create_error_embed(
                    title="Error Creating Organization",
                    description=str(e)
                ),
                ephemeral=True
            )

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
        placeholder="Enter: seconds, minutes, hours, or days",
        required=True,
        min_length=4,
        max_length=7
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

            if total_points < amount:
                raise ValueError("Total points pool must be greater than or equal to the payment amount!")

            session = interaction.client.db_manager.Session()
            try:
                # Get organization name
                org = session.query(Organization).filter_by(id=self.org_id).first()
                org_name = org.name if org else "Unknown Organization"
                
                schedule = PaymentSchedule(
                    organization_id=self.org_id,
                    amount=amount,
                    interval_value=interval_value,
                    interval_type=IntervalType(interval_type),
                    total_points=total_points,
                    points_paid=0
                )
                session.add(schedule)
                session.commit()

                # Start the payment schedule immediately
                members = session.query(OrganizationMember).filter_by(
                    organization_id=self.org_id
                ).all()

                if members:
                    points_per_member = amount // len(members)
                    if points_per_member > 0:
                        successful_distributions = 0
                        points_manager = interaction.client.points_manager

                        # Distribute initial payment with correct method signature
                        for member in members:
                            try:
                                await points_manager.add_points(
                                    user_id=int(member.user_id),
                                    amount=points_per_member
                                )
                                successful_distributions += 1
                            except Exception as e:
                                print(f"Error distributing points to {member.user_id}: {e}")

                        # Update schedule with initial payment
                        total_distributed = points_per_member * successful_distributions
                        schedule.points_paid = total_distributed
                        schedule.last_paid_at = datetime.utcnow()  # Update last paid time
                        session.commit()

                        # Add success info to the embed
                        initial_payment_info = (
                            f"\n\n**📊 Initial Payment**\n"
                            f"• Points per member: {points_per_member:,}\n"
                            f"• Recipients: {successful_distributions}\n"
                            f"• Total distributed: {total_distributed:,}"
                        )
                else:
                    initial_payment_info = "\n\n**⚠️ Note:** No members to distribute points to yet."

                # Calculate human-readable time estimate
                total_payments = total_points // amount
                time_in_seconds = interval_value * {
                    'seconds': 1,
                    'minutes': 60,
                    'hours': 3600,
                    'days': 86400
                }[interval_type]
                total_time_seconds = time_in_seconds * total_payments
                
                # Convert to most appropriate unit
                time_str = ""
                if total_time_seconds < 60:
                    time_str = f"{total_time_seconds} seconds"
                elif total_time_seconds < 3600:
                    minutes = total_time_seconds // 60
                    time_str = f"{minutes} minutes"
                elif total_time_seconds < 86400:
                    hours = total_time_seconds // 3600
                    time_str = f"{hours} hours"
                else:
                    days = total_time_seconds // 86400
                    time_str = f"{days} days"

                embed = create_success_embed(
                    title="Payment Schedule Created",
                    description=(
                        "### Schedule Details\n"
                        f"Successfully created a new payment schedule!\n\n"
                        f"**💰 Payment Amount:** {amount:,} points\n"
                        f"⏱️ **Interval:** Every {interval_value} {interval_type}\n"
                        f"🎯 **Total Pool:** {total_points:,} points\n"
                        f"📊 **Total Payments:** {total_payments}\n"
                        f"⌛ **Estimated Duration:** {time_str}"
                        f"{initial_payment_info}\n\n"
                        "**💡 Quick Tip**\n"
                        "The next payment will occur after one interval!"
                    )
                )
                
                # Update the Menu cog's last payment time for this schedule
                menu_cog = interaction.client.get_cog('Menu')
                if menu_cog:
                    menu_cog.last_payment_time[schedule.id] = datetime.utcnow()
                
                view = PaymentScheduleView(self.org_id, org_name)
                await interaction.response.edit_message(embed=embed, view=view)
                
            finally:
                session.close()

        except ValueError as e:
            embed = create_error_embed(
                title="Invalid Input",
                description=(
                    "### Error Creating Schedule\n"
                    f"{str(e)}\n\n"
                    "**🔍 Requirements**\n"
                    "• All numbers must be positive\n"
                    "• Interval type must be: seconds, minutes, hours, or days\n"
                    "• Total points must be greater than payment amount\n\n"
                    "**💡 Example**\n"
                    "Amount: 1000\n"
                    "Interval: 24\n"
                    "Type: hours\n"
                    "Total: 10000"
                )
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class PaymentScheduleView(discord.ui.View):
    def create_progress_bar(self, current: int, total: int, width: int = 10) -> str:
        filled = '█'
        empty = '░'
        progress = current / total
        filled_amount = round(width * progress)
        empty_amount = width - filled_amount
        
        # Calculate percentage
        percentage = progress * 100
        
        # Create the progress bar with percentage
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
                
                for schedule in schedules:
                    points_paid = schedule.points_paid or 0
                    remaining_points = schedule.total_points - points_paid
                    remaining_payments = remaining_points // schedule.amount
                    
                    # Calculate time until next payment
                    interval_seconds = schedule.interval_value * {
                        'seconds': 1,
                        'minutes': 60,
                        'hours': 3600,
                        'days': 86400
                    }[schedule.interval_type.value]
                    
                    # Create progress bar
                    progress_bar = self.create_progress_bar(points_paid, schedule.total_points, width=15)
                    
                    embed.add_field(
                        name=f"Schedule #{schedule.id}",
                        value=(
                            f"💰 **Amount:** {schedule.amount:,} points\n"
                            f"⏱️ **Interval:** {schedule.interval_value} {schedule.interval_type.value}\n"
                            f"📈 **Progress:**\n"
                            f"`{progress_bar}`\n"
                            f"**Points Distributed:** {points_paid:,} / {schedule.total_points:,}\n"
                            f"🎯 **Remaining Payments:** {remaining_payments}\n"
                            f"💫 **Payment Rate:** {schedule.amount:,} points per {schedule.interval_value} {schedule.interval_type.value}"
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
                "• Automated payment systems\n"
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
                        "• Create new organizations\n"
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

class Menu(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.payment_task = self.bot.loop.create_task(self.process_payments())
        self.last_payment_time = {}

    async def process_payments(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                session = self.bot.db_manager.Session()
                try:
                    schedules = session.query(PaymentSchedule).all()
                    current_time = datetime.utcnow()

                    for schedule in schedules:
                        # Skip completed schedules
                        if schedule.points_paid >= schedule.total_points:
                            continue

                        # Use last_paid_at from database instead of local tracking
                        time_since_last = current_time - schedule.last_paid_at

                        interval_seconds = schedule.interval_value * {
                            'seconds': 1,
                            'minutes': 60,
                            'hours': 3600,
                            'days': 86400
                        }[schedule.interval_type.value]

                        # Check if it's time for payment
                        if time_since_last.total_seconds() >= interval_seconds:
                            members = session.query(OrganizationMember).filter_by(
                                organization_id=schedule.organization_id
                            ).all()

                            if members:
                                points_per_member = schedule.amount // len(members)
                                remaining_points = schedule.total_points - schedule.points_paid
                                
                                if points_per_member * len(members) > remaining_points:
                                    points_per_member = remaining_points // len(members)

                                if points_per_member > 0:
                                    successful_distributions = 0
                                    
                                    # Use bot's points manager
                                    for member in members:
                                        try:
                                            await self.bot.points_manager.add_points(
                                                user_id=int(member.user_id),
                                                amount=points_per_member
                                            )
                                            successful_distributions += 1
                                        except Exception as e:
                                            print(f"Error distributing points to {member.user_id}: {e}")

                                    # Update schedule
                                    total_distributed = points_per_member * successful_distributions
                                    schedule.points_paid += total_distributed
                                    schedule.last_paid_at = current_time
                                    session.commit()

                                    # Send notification
                                    try:
                                        org = session.query(Organization).filter_by(
                                            id=schedule.organization_id
                                        ).first()
                                        
                                        embed = create_basic_embed(
                                            title="Points Distribution",
                                            description=(
                                                f"### Payment Complete\n"
                                                f"Organization: **{org.name}**\n\n"
                                                f"**💰 Per Member:** {points_per_member:,} points\n"
                                                f"**👥 Recipients:** {successful_distributions}\n"
                                                f"**📊 Total Distributed:** {total_distributed:,} points\n"
                                                f"**🎯 Progress:** {schedule.points_paid:,}/{schedule.total_points:,} points"
                                            )
                                        )
                                        
                                        # Notify organization owner
                                        if org and org.owner_id:
                                            try:
                                                owner = await self.bot.fetch_user(int(org.owner_id))
                                                if owner:
                                                    await owner.send(embed=embed)
                                            except discord.HTTPException:
                                                pass  # Failed to DM owner
                                    except Exception as e:
                                        print(f"Error sending notification: {e}")

                finally:
                    session.close()
            except Exception as e:
                print(f"Error in payment processing: {e}")

            await asyncio.sleep(30)

    @app_commands.command(name="start", description="Open the organization management hub")
    async def start(self, interaction: discord.Interaction):
        embed = create_basic_embed(
            title="Welcome to Organization Hub",
            description=(
                "### Your Command Center\n"
                "Streamline your organization management.\n\n"
                "**🎯 Key Features**\n"
                "• Create and manage organizations\n"
                "• Add and remove members\n"
                "• Set up automated payments\n"
                "• Track organization metrics\n\n"
                "**🚀 Getting Started**\n"
                "• Create your first organization\n"
                "• Add team members\n"
                "• Set up payment schedules\n\n"
                "**💡 Quick Tip**\n"
                "Use `/help` for detailed command information!"
            )
        )
        view = MainMenuView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Menu(bot)) 