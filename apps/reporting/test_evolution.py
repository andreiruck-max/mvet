from datetime import date
from decimal import Decimal as D
from unittest.mock import patch
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from . import evolution as e, selectors
from .tests import ReportingFixture


class CalendarTests(SimpleTestCase):
    def test_short_month_leap_year_and_cutover(self):
        rows=e.ranges(date(2028,3,31),date(2028,1,15),'month')
        self.assertEqual(rows[-2]['comparable_end'],date(2028,2,29))
        self.assertEqual(rows[0]['start'],date(2028,1,15))
        self.assertFalse(rows[0]['complete_start'])
        years=e.ranges(date(2028,2,29),date(2026,9,15),'year')
        self.assertEqual(years[-2]['comparable_end'],date(2027,2,28))
        self.assertFalse(years[0]['comparable_available'])
        self.assertEqual(e.month_start(date(2026,1,8),-1),date(2025,12,1))

    def test_forecast_relative_daily_empty_and_closed_month(self):
        current=selectors.metrics({'products_amount':D(200),'cmv':D(250),'count':2})
        previous=selectors.metrics({'products_amount':D(1000),'count':10})
        part=selectors.metrics({'products_amount':D(100),'count':1})
        args=dict(as_of=date(2026,11,8),cutover=date(2026,9,15))
        result=e.estimate(current,previous,part,**args)
        self.assertEqual(result['values']['revenue'],2000)
        self.assertEqual(result['values']['contribution'],-500)
        empty=selectors.metrics({})
        result=e.estimate(current,previous,empty,**args)
        self.assertEqual(result['values']['revenue'],750)
        self.assertFalse(e.estimate(empty,previous,part,**args)['available'])
        self.assertFalse(e.estimate(current,previous,part,as_of=date(2026,11,8),cutover=date(2026,11,2))['available'])
        closed=e.estimate(current,previous,part,as_of=date(2026,11,30),cutover=date(2026,9,15))
        self.assertEqual(closed['values']['revenue'],200)
        self.assertIsNone(e.variation(D(10),D(0)))
        self.assertIsNone(e.variation(D(10),D(-1)))


class EvolutionTests(ReportingFixture,TestCase):
    def setUp(self):
        clock=patch('django.utils.timezone.localdate',return_value=date(2026,11,8))
        clock.start();self.addCleanup(clock.stop)
        super().setUp()
        self.company.cutover_date=date(2026,9,15);self.company.save()
        for number,day,amount in [('1',date(2026,10,8),100),('2',date(2026,10,20),300),('3',self.today,200)]:
            self.confirmed(invoice_number=number,date=day,products_amount=D(amount),discount=D(0),shipping_received=D(0))

    def test_comparison_totals_averages_and_whole_month_expenses(self):
        self.expense(amount=D(90),competence=date(2026,11,30))
        result=e.report(self.actor,self.today)
        self.assertEqual(result['current']['revenue'],200)
        self.assertEqual(result['previous']['revenue'],100)
        self.assertEqual(result['change'],100)
        self.assertEqual(result['summary']['values']['revenue'],600)
        self.assertEqual(result['summary']['monthly_revenue'],200)
        self.assertEqual(result['summary']['values']['ticket'],200)
        self.assertEqual(result['summary']['values']['cmv'],30)
        self.assertEqual(result['projection']['values']['revenue'],800)
        self.assertEqual(result['projection']['recorded_charges'],90)
        self.assertEqual(result['projection']['result'],result['current']['contribution']*4-90)
        self.assertEqual(result['summary']['result'],selectors.dre(dict(start=self.company.cutover_date,end=self.today))['result'])
        self.assertIsNone(result['rows'][0]['full_change'])
        self.assertIsNone(result['rows'][-1]['comparable'])
        self.assertEqual(result['rows'][-1]['full']['count'],0)
        annual=e.report(self.actor,self.today,'year')
        self.assertEqual(annual['summary']['values'],result['summary']['values'])
        self.assertEqual(annual['summary']['result'],result['summary']['result'])
        self.assertEqual(annual['summary']['monthly_revenue'],200)

    def test_channel_permissions_and_http_validation(self):
        channel=e.report(self.actor,self.today,channel=self.channel)
        self.assertFalse(channel['can_result'])
        self.assertNotIn('result',channel['projection'])
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('report_evolution')).status_code,403)
        self.operator.user_permissions.add(Permission.objects.get(codename='view_dashboard'))
        response=self.client.get(reverse('report_evolution'))
        self.assertEqual(response.status_code,200)
        result=response.context['analysis']
        self.assertNotIn('cmv',result['summary']['values'])
        self.assertNotIn('contribution',result['projection']['values'])
        self.assertNotIn('result',result['projection'])
        self.assertNotContains(response,'CMV total')
        for query in ({'as_of':'2026-11-09'},{'as_of':'2026-09-14'},{'grouping':'invalid'},{'channel':'99999'}):
            self.assertEqual(self.client.get(reverse('report_evolution'),query).status_code,400)
        self.client.force_login(self.actor)
        self.assertContains(self.client.get(reverse('report_evolution'),{'grouping':'year'}),'Média por ano')
        self.assertContains(self.client.get(reverse('dashboard')),'data-card="cmv"')
        self.assertEqual(self.client.post(reverse('dashboard_order'),data='{"order":["cmv","revenue"]}',content_type='application/json').status_code,200)
