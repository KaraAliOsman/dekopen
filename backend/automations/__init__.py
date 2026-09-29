"""Domain automations — §08: consequential workflow events queue durable jobs
(freeze → material forecast, optimize/release shortage → purchase task, missing
catalog authority → catalog task, payment → commercial refresh, station
complete → next-step notice) so follow-on work survives the request and retries
through the job layer instead of silently disappearing."""
