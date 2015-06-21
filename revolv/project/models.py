
import datetime
from itertools import chain

from ckeditor.fields import RichTextField
from django.core.urlresolvers import reverse
from django.db import models
from imagekit.models import ImageSpecField, ProcessedImageField
from imagekit.processors import ResizeToFill
from revolv.base.models import RevolvUserProfile
from revolv.lib.utils import ImportProxy
from revolv.payments.models import Payment
from revolv.project.stats import KilowattStatsAggregator


class ProjectManager(models.Manager):
    """
    Manager for running custom operations on the Projects.
    """

    def get_featured(self, num_projects, queryset=None):
        """ Get num_projects amount of active projects. If we don't have
        enough active projects, then we retrieve completed projects. This
        function may return fewer projects than requested if not enough exist.

        :num_projects: Number of projects to be retrieved
        :queryset: The queryset in which to search for projects
        :return: A list of featured project objects
        """
        if queryset is None:
            queryset = super(ProjectManager, self).get_queryset()
        featured_projects = queryset.filter(
            project_status=Project.ACTIVE).order_by(
            'end_date')[:num_projects]
        if featured_projects.count() < num_projects:
            num_completed_needed = num_projects - featured_projects.count()
            completed_projects = queryset.filter(
                project_status=Project.COMPLETED).order_by(
                'end_date')[:num_completed_needed]
            return list(chain(featured_projects, completed_projects))
        else:
            return featured_projects

    def get_completed(self, queryset=None):
        """ Gets all the projects that have been completed funding.

        :queryset: The queryset in which to search for projects
        :return: A list of completed project objects
        """
        if queryset is None:
            queryset = super(ProjectManager, self).get_queryset()
        completed_projects = queryset.filter(
            project_status=Project.COMPLETED
        ).order_by('end_date')
        return completed_projects

    def get_active(self, queryset=None):
        """ Gets all the projects that have been active to go into funding.

        :queryset: The queryset in which to search for projects
        :return: A list of active project objects
        """
        if queryset is None:
            queryset = super(ProjectManager, self).get_queryset()
        active_projects = queryset.filter(
            project_status=Project.ACTIVE
        ).order_by('end_date')
        return active_projects

    def get_proposed(self, queryset=None):
        """ Gets all the projects that are currently in review (proposed).

        :queryset: The queryset in which to search for projects
        :return: A list of in review project objects
        """
        if queryset is None:
            queryset = super(ProjectManager, self).get_queryset()
        proposed_projects = queryset.filter(
            project_status=Project.PROPOSED
        ).order_by('updated_at')
        return proposed_projects

    def get_drafted(self, queryset=None):
        """ Get all the projects that are drafted in the queryset.

        :queryset: The queryset in which to search for projects
        :return: A list of in review project objects
        """
        if queryset is None:
            queryset = super(ProjectManager, self).get_queryset()
        drafted_projects = queryset.filter(
            project_status=Project.DRAFTED
        ).order_by('updated_at')
        return drafted_projects

    def statistics(self, queryset=None):
        """
        Return a revolv.project.stats.KilowattStatsAggregator to
        aggregate statistics about the impact of the given queryset of
        projects.
        """
        if queryset is None:
            queryset = super(ProjectManager, self).get_queryset()
        return KilowattStatsAggregator.from_project_queryset(queryset)

    def owned_projects(self, user_profile):
        """ Get all projects owned by a RevolvUserProfile.

        :user: The user of interest
        :return: A list of projects for which user's RevolvUserProfile
        is the ambassador
        """
        return Project.objects.filter(ambassador=user_profile)

    def donated_projects(self, user_profile):
        """
        :return: Projects to which this RevolvUserProfile has donated
        """
        return user_profile.project_set.all()

    def create_from_form(self, form, ambassador):
        """ Creates project from form and sets ambassador to a RevolvUserProfile.

        :form: The form
        :ambassador: The RevolvUserProfile of the ambassador of the project
        :return: Project created and saved
        """
        project = form.save(commit=False)
        project.ambassador = ambassador
        project.save()
        return project


class Project(models.Model):
    """
    Project model. Stores basic metadata, information about the project,
    donations, energy impact, goals, and info about the organization.
    """
    ACTIVE = 'AC'
    PROPOSED = 'PR'
    COMPLETED = 'CO'
    DRAFTED = 'DR'
    PROJECT_STATUS_CHOICES = (
        (ACTIVE, 'Active'),
        (PROPOSED, 'Proposed'),
        (COMPLETED, 'Completed'),
        (DRAFTED, 'Drafted'),
    )
    LESS_THAN_ONE_DAY_LEFT_STATEMENT = "only hours left"
    NO_DAYS_LEFT_STATEMENT = "deadline reached"

    funding_goal = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text='How much do you aim to raise for this project?'
    )
    title = models.CharField(
        max_length=255,
        help_text='How would you like to title this project?'
    )
    tagline = models.CharField(
        max_length=100,
        null=True,
        blank=False,
        help_text='Select a short tag line that describes this project. (No more than 100 characters.)'
    )
    video_url = models.URLField(
        'Video URL',
        max_length=255,
        blank=True,
        help_text='Optional: Link to a Youtube video about the project or community.'
    )
    # power output of array in kilowatts
    impact_power = models.FloatField(
        'Expected Killowatt Output',
        help_text='What is the expected output in killowatts of the proposed solar array?'
    )
    # solar log graphics url
    solar_url = models.URLField(
        'Solar Log Graphics URL',
        max_length=255,
        blank=True,
        help_text='This can be found by going to http://home.solarlog-web.net/, going to the \
        solar log profile for your site, and clicking on the Graphics sub-page. Copy and paste \
        the URL in the address bar into here.'
    )
    location = models.CharField(
        'Organization Address',
        max_length=255,
        help_text='What is the address of the organization where the solar panels will be installed?'
    )
    # latitude and longitude of the organization location
    location_latitude = models.DecimalField(
        max_digits=17,
        decimal_places=14,
        default=0.0
    )
    location_longitude = models.DecimalField(
        max_digits=17,
        decimal_places=14,
        default=0.0
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    end_date = models.DateField(
        help_text='When will this crowdfunding project end?'
    )
    project_status = models.CharField(
        max_length=2,
        choices=PROJECT_STATUS_CHOICES,
        default=DRAFTED
    )
    cover_photo = ProcessedImageField(
        upload_to='covers/',
        processors=[ResizeToFill(1200, 500)],
        format='JPEG',
        options={'quality': 80},
        default=None,
        help_text='Choose a beautiful high resolution image to represent this project.',
        blank=True
    )
    preview_photo = ImageSpecField(
        source='cover_photo',
        processors=[ResizeToFill(400, 300)],
        format='JPEG',
        options={'quality': 80},
    )
    org_start_date = models.DateField(
        'Organization Founding Date',
        blank=True,
        null=True,
        help_text='When was the organization being helped established?'
    )

    org_name = models.CharField(
        'Organization Name',
        max_length=255,
        help_text='What is the name of the organization being helped?'
    )

    mission_statement = models.TextField(
        'Organization Mission',
        help_text='What is the mission statement of the organization being helped by this project?',
    )

    org_about = models.TextField(
        'Organization Description',
        help_text='Elaborate more about the organization, what it does, who it serves, etc.'
    )

    description = RichTextField(
        'Project description',
        help_text='This is the body of content that shows up on the project page.'
    )

    donors = models.ManyToManyField(RevolvUserProfile, blank=True)

    ambassador = models.ForeignKey(RevolvUserProfile, related_name='ambassador')

    # energy produced in kilowatt hours
    actual_energy = models.FloatField(default=0.0)
    internal_rate_return = models.DecimalField(
        'Internal Rate of Return',
        max_digits=6,
        decimal_places=3,
        default=0.0,
        help_text='The internal rate of return for this project.'
    )

    # solar data csv files
    daily_solar_data = models.FileField(blank=True, null=True, upload_to="projects/daily/")
    monthly_solar_data = models.FileField(blank=True, null=True, upload_to="projects/monthly/")
    annual_solar_data = models.FileField(blank=True, null=True, upload_to="projects/annual/")

    objects = ProjectManager()
    factories = ImportProxy("revolv.project.factories", "ProjectFactories")

    def has_owner(self, ambassador):
        return self.ambassador == ambassador

    def approve_project(self):
        self.project_status = Project.ACTIVE
        self.save()
        return self

    def unapprove_project(self):
        """
        TODO (https://github.com/calblueprint/revolv/issues/255): when we add
        a STAGED project status, the "unapprove" action should make the project
        STAGED, not PROPOSED.
        """
        self.project_status = Project.PROPOSED
        self.save()
        return self

    def propose_project(self):
        self.project_status = Project.PROPOSED
        self.save()
        return self

    def deny_project(self):
        self.project_status = Project.DRAFTED
        self.save()
        return self

    def complete_project(self):
        self.project_status = Project.COMPLETED
        self.save()
        return self

    def mark_as_incomplete_project(self):
        self.project_status = Project.ACTIVE
        self.save()
        return self

    def update_categories(self, category_list):
        """ Updates the categories list for the project.

        :category_list The list of categories in the submitted form
        """
        # Clears all the existing categories
        self.category_set.clear()

        # Adds the list of categories to the project
        for category in category_list:
            category_object = Category.objects.get(title=category)
            self.category_set.add(category_object)

    def get_absolute_url(self):
        return reverse("project:view", kwargs={"pk": str(self.pk)})

    def get_organic_donations(self):
        return self.payment_set.exclude(user__isnull=True).filter(
            entrant__pk=models.F('user__pk')
        )

    def proportion_donated(self, user):
        """
        :return:
            The proportion that this user has organically donated to this
            project as a float in the range [0, 1] (inclusive)
        """
        user_donation = Payment.objects.donations(
            project=self,
            user=user,
            organic=True
        ).aggregate(
            models.Sum('amount')
        )['amount__sum'] or 0.0
        prop = user_donation / self.amount_donated_organically
        assert 0 <= prop <= 1, "proportion_donated is incorrect!"
        return prop

    @property
    def amount_donated_organically(self):
        """
        :return: the current total amount that has been organically donated to
        this project, as a float
        """
        return self.get_organic_donations().aggregate(
            models.Sum('amount')
        )["amount__sum"] or 0.0

    @property
    def location_street(self):
        """
        :return: a string of the street name of the location of this project.
        If the project location is malformed, will return an empty string.
        """
        try:
            return self.location.split(',')[0]
        except IndexError:
            return ""

    @property
    def location_city_state_zip(self):
        """
        :return: a string of the city, state, and zip code of the location of this project.
        If the project location is malformed, will return an empty string.
        """
        try:
            pieces = self.location.split(',')
            if len(pieces) >= 3:
                return pieces[1] + "," + pieces[2]
            elif len(pieces) == 2:
                return pieces[1]
            return pieces[0]
        except IndexError:
            return ""

    @property
    def amount_donated(self):
        """
        :return: the current total amount that has been donated to this project,
            as a float
        """
        return self.payment_set.aggregate(
            models.Sum('amount')
        )["amount__sum"] or 0.0

    @property
    def amount_left(self):
        """
        :return: the current amount of money needed for this project to
            reach its goal, as a float.
        """
        amt_left = float(self.funding_goal) - self.amount_donated
        if amt_left < 0:
            return 0.0
        return amt_left

    @property
    def amount_repaid(self):
        """
        :return: the current amount of money repaid by the project to RE-volv.
        """
        return self.adminrepayment_set.aggregate(models.Sum('amount'))["amount__sum"] or 0.0

    @property
    def total_amount_to_be_repaid(self):
        """
        :return: the total amount of money to be repaid by the project to RE-volv.
        """
        # TODO (https://github.com/calblueprint/revolv/issues/291): Actually
        # calculate this amount based off of interest, but using the project's
        # funding goal is sufficient for now.
        return self.funding_goal

    @property
    def rounded_amount_left(self):
        """
        :return: The amount needed to complete this project, floored to the nearest
            dollar.

        Note: if for some reason the amount left is negative, this will perform a
        ceiling operation instead of a floor, but that should never happen.
        """
        return int(self.amount_left)

    @property
    def partial_completeness(self):
        """
        :return: a float between 0 and 1, representing the completeness of this
            project with respect to its goal (1 if exactly the goal amount, or
            more, has been donated, 0 if nothing has been donated).
        """
        ratio = self.amount_donated / float(self.funding_goal)
        return min(ratio, 1.0)

    @property
    def percent_complete(self):
        """
        :return: a floored int between 0 and 100, representing the completeness of this
            project with respect to its goal (100 if exactly the goal amount, or
            more, has been donated, 0 if nothing has been donated).
        """
        return int(self.partial_completeness * 100)

    def partial_completeness_as_js(self):
        return unicode(self.partial_completeness)

    @property
    def percent_repaid(self):
        """
        :return: a floored int between 0 and 100, representing the amount repaid
        in respect to its repayment goal (100 if exactly the goal amount, or
        more, has been donated, 0 if nothing has been donated).
        """
        return int(self.partial_repayment * 100)

    @property
    def partial_repayment(self):
        """
        :return: a float between 0 and 1, representing the repayment progress
        of this project with respect to the repayment goal (1 if exactly the
        goal amount, or more, has been donated, 0 if nothing has been donated).
        """
        ratio = self.amount_repaid / float(self.total_amount_to_be_repaid)
        return min(ratio, 1.0)

    def partial_repayment_as_js(self):
        return unicode(self.partial_repayment)

    @property
    def days_until_end(self):
        return (datetime.date.today() - self.end_date).days

    @property
    def days_left(self):
        return max(self.days_until_end, 0)

    def formatted_days_left(self):
        days_left = self.days_until_end
        if days_left == 1:
            return "1 day left"
        if days_left == 0:
            return self.LESS_THAN_ONE_DAY_LEFT_STATEMENT
        if days_left < 0:
            return self.NO_DAYS_LEFT_STATEMENT
        return unicode(days_left) + " days left"

    @property
    def is_active(self):
        return self.project_status == Project.ACTIVE

    @property
    def is_proposed(self):
        return self.project_status == Project.PROPOSED

    @property
    def is_drafted(self):
        return self.project_status == Project.DRAFTED

    @property
    def is_completed(self):
        return self.project_status == Project.COMPLETED

    @property
    def status_display(self):
        return dict(Project.PROJECT_STATUS_CHOICES)[self.project_status]

    @property
    def categories(self):
        return [category.title for category in self.category_set.all()]

    @property
    def updates(self):
        """
        :return: The set of all ProjectUpdate models associated with this project.
        """
        return self.updates.all()

    @property
    def donation_levels(self):
        """
        :return: The set of all DonationLevel models associated with this project.
        """
        return self.donationlevel_set.all()

    @property
    def statistics(self):
        """
        Return a revolv.project.stats.KilowattStatsAggregator for this project.
        Having this as a property is usefule in templates where we need to display
        statistics about the project (e.g. lbs carbon saved, $ saved, etc).
        """
        return KilowattStatsAggregator.from_project(self)

    def add_update(self, text):
        update = ProjectUpdate(update_text=text, project=self)
        update.save()


class ProjectUpdate(models.Model):
    factories = ImportProxy("revolv.project.factories", "ProjectUpdateFactories")
    update_text = RichTextField(
        'Update content',
        help_text="What should be the content of the update?"
    )

    date = models.DateField(
        'Date of update creation',
        help_text="What time was the update created?",
        auto_now_add=True
    )

    project = models.ForeignKey(
        Project,
        related_name="updates"
    )


class Category(models.Model):
    """
    Categories that a project is associated with. Categories are predefined,
    and as of now, loaded through fixtures.
    """
    HEALTH = 'Health'
    ARTS = 'Arts'
    FAITH = 'Faith'
    EDUCATION = 'Education'
    COMMUNITY = 'Community'
    GEOGRAPHIC = 'Geographic'

    valid_categories = [HEALTH, ARTS, FAITH, EDUCATION, COMMUNITY, GEOGRAPHIC]

    factories = ImportProxy("revolv.project.factories", "CategoryFactories")

    title = models.CharField(max_length=50, unique=True)
    projects = models.ManyToManyField(Project)

    def __unicode__(self):
        return self.title


class DonationLevel(models.Model):
    """
    Model to track donation levels and perks for projects.
    """
    project = models.ForeignKey(Project)
    description = models.TextField()
    amount = models.IntegerField()
