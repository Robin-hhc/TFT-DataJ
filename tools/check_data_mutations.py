"""Temporary in-process faults. Source files are never edited."""
import argparse
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'outputs/companion'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,default=ROOT/'outputs/companion/fixtures/data_display/matrix.json.gz')
    parser.add_argument('--report',type=Path,default=ROOT/'work/data-validation/mutations.json')
    args=parser.parse_args()
    from display_audit import DisplayReplay
    from test_equipment_display import EquipmentDisplayTests
    from test_display_lifecycle import DisplayLifecycle
    from dataj import DataJ
    from comp_browser import CompBrowser
    from bug_reporting import BugReporter
    from hex_prewarm import HexPrewarm
    from test_hex_prewarm_recovery import HexPrewarmRecoveryTests
    from test_hex_failure_diagnostics import HexFailureDiagnosticsTests
    from test_source_failure_details import SourceFailureDetailsTests
    from test_title_catalog_boundary import TitleCatalogBoundaryTests
    from test_validated_cache import ValidatedCacheTests
    from test_startup_versions import StartupVersions
    import core
    import source_failures
    import hex_results
    import item_controller
    replay=DisplayReplay(args.fixture);results=[]
    def unit(cls,name):
        result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.TestSuite([cls(name)]))
        assert result.wasSuccessful(),str(result.failures or result.errors)
    def check(name,context,case):
        case()  # A failing baseline must never be mistaken for a caught mutant.
        with context:
            try:case()
            except AssertionError as exc:results.append({'fault':name,'status':'caught','evidence':str(exc)[:1000]})
            else:results.append({'fault':name,'status':'escaped'})
    try:
        check('remove hero sample threshold',patch('app.COMP_MIN_SAMPLE',0),
              lambda:unit(EquipmentDisplayTests,'test_real_single_equipment_matches_site_filtered_rows'))
        runes=replay.matrix['hexes'][3:6]
        original_stage=hex_results.stage_stat
        check('use 2-1 statistics at 4-2',patch('hex_results.stage_stat',lambda rows,entity,stage:original_stage(rows,entity,'2-1')),
              lambda:replay.hex('18.2a','112','4-2',runes))
        original_hexes=DataJ.hexes
        check('swap global and pinned comp statistics',patch.object(DataJ,'hexes',lambda self,comp=None:original_hexes(self,None if comp else '112')),
              lambda:replay.hex('18.2a','112','3-2',runes))
        check('reuse item memory cache across versions',patch('item_controller.query_key',lambda adapter,kind,scope:(18,'18.2a',kind,scope)),
              lambda:unit(DisplayLifecycle,'test_all_screens_version_a_b_a_and_cache'))
        original_render=item_controller.ItemController.render
        def wrong_slots(controller):
            controller.rows.reverse()
            try:return original_render(controller)
            finally:controller.rows.reverse()
        check('reverse item overlay slots',patch.object(item_controller.ItemController,'render',wrong_slots),
              lambda:replay.items('18.2a',None,replay.matrix['items'][3:6]))
        check('visible augment panel never updates',patch('ui_theme.ResultCard.update_statistics',lambda *args:None),
              lambda:replay.hex('18.2a','112','3-2',runes))
        original_comp_render=CompBrowser.render
        def reversed_comp_ranks(browser):
            original_comp_render(browser)
            browser.cards.reverse()
            for card in browser.cards:browser.card_layout.removeWidget(card)
            for index,card in enumerate(browser.cards):browser.card_layout.insertWidget(index,card)
        rank_record=next(r for r in replay.records if r['request']['path']=='/comp/rank'
                         and r['request']['params']['gameVersion']=='18.2a')
        check('reverse visible comp ranking',patch.object(CompBrowser,'render',reversed_comp_ranks),
              lambda:replay.explorer(rank_record,0))
        original_holders=item_controller.best_holders
        check('reverse item holder ranking',patch('item_controller.best_holders',
              lambda *args,**kwargs:list(reversed(original_holders(*args,**kwargs)))),
              lambda:replay.items('18.2a',None,replay.matrix['items'][:3]))
        check('never resume failed augment prewarm',patch.object(HexPrewarm,'_schedule_retry_locked',lambda *args:None),
              lambda:unit(HexPrewarmRecoveryTests,'test_transient_http_failure_automatically_resumes_pending_exact_stages_after_cooldown'))
        original_send=DataJ._send_request
        def accept_invalid_source(adapter,client,method,path,params,body,key,validate=None):
            return original_send(adapter,client,method,path,params,body,key,None)
        check('publish invalid augment main table before domain validation',patch.object(DataJ,'_send_request',accept_invalid_source),
              lambda:unit(ValidatedCacheTests,'test_invalid_hex_refresh_cannot_replace_last_good_statistics'))
        original_cached=DataJ._cached_request
        def accept_invalid_cache(adapter,path,key,ttl,validate=None):
            return original_cached(adapter,path,key,ttl,None)
        check('reuse legacy invalid persisted values without domain validation',patch.object(DataJ,'_cached_request',accept_invalid_cache),
              lambda:unit(ValidatedCacheTests,'test_legacy_bad_entries_are_repaired_for_each_public_query'))
        check('lose last good local catalog after failed refresh',patch.object(DataJ,'catalog_snapshot',lambda adapter:None),
              lambda:unit(StartupVersions,'test_expired_local_catalog_survives_bad_refresh_without_old_statistics'))
        original_report=BugReporter.hex_statistics
        def omit_partial_failure(reporter,reason,**kwargs):
            return False if reason=='hex_comp_supplement_failed' else original_report(reporter,reason,**kwargs)
        check('omit partial augment failure archive',patch.object(BugReporter,'hex_statistics',omit_partial_failure),
              lambda:unit(HexFailureDiagnosticsTests,'test_partial_timeout_archives_exact_failure_and_preserves_two_successes'))
        original_resolve=core.resolve_name
        def hide_catalog_reason(*args,**kwargs):
            result=original_resolve(*args,**kwargs);result.pop('reason',None);return result
        check('hide missing exact catalog title reason',patch('test_title_catalog_boundary.resolve_name',hide_catalog_reason),
              lambda:unit(TitleCatalogBoundaryTests,'test_repeated_missing_title_is_reported_as_catalog_lookup_failure_without_an_id'))
        original_details=source_failures.source_failure_details
        def forget_origin(*args,**kwargs):
            result=original_details(*args,**kwargs);result.pop('cooldown_origin',None);return result
        check('drop triggering shared cooldown failure',patch('test_source_failure_details.source_failure_details',forget_origin),
              lambda:unit(SourceFailureDetailsTests,'test_exact_query_cooldown_retains_the_actual_prior_http_failure_origin'))
        original_explore=DataJ.explore
        from dataj import SourceError
        def forget_request(adapter,*args,**kwargs):
            try:return original_explore(adapter,*args,**kwargs)
            except SourceError as error:
                if hasattr(error,'request_details'):del error.request_details
                raise
        check('record caller alias instead of actual augment request',patch.object(DataJ,'explore',forget_request),
              lambda:unit(SourceFailureDetailsTests,'test_prewarm_failure_records_the_canonical_body_that_actually_reached_http'))
    finally:replay.close()
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps({'cases':results},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(results,ensure_ascii=False))
    return int(len(results)!=16 or any(r['status']!='caught' for r in results))


if __name__=='__main__':raise SystemExit(main())
