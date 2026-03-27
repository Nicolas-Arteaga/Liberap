using System;
using System.Collections.Generic;
using System.Linq;
using System.Linq.Dynamic.Core;
using System.Threading.Tasks;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Application.Services;
using Volo.Abp.Domain.Repositories;
using Verge.Trading.DTOs;

namespace Verge.Trading;

public class AlertHistoryAppService : ApplicationService, IAlertHistoryAppService
{
    private readonly IRepository<AlertHistory, Guid> _alertHistoryRepository;

    public AlertHistoryAppService(IRepository<AlertHistory, Guid> alertHistoryRepository)
    {
        _alertHistoryRepository = alertHistoryRepository;
    }

    public async Task<PagedResultDto<AlertHistoryDto>> GetListAsync(GetAlertHistoryInput input)
    {
        var query = await _alertHistoryRepository.GetQueryableAsync();

        if (!string.IsNullOrWhiteSpace(input.Symbol))
        {
            query = query.Where(x => x.Symbol == input.Symbol);
        }

        if (!string.IsNullOrWhiteSpace(input.Style))
        {
            query = query.Where(x => x.Style == input.Style);
        }

        if (!string.IsNullOrWhiteSpace(input.Status))
        {
            query = query.Where(x => x.Status == input.Status);
        }

        if (input.IsRead.HasValue)
        {
            query = query.Where(x => x.IsRead == input.IsRead.Value);
        }

        var totalCount = await AsyncExecuter.CountAsync(query);

        var items = await AsyncExecuter.ToListAsync(
            query.OrderByDescending(x => x.EmittedAt) // Default sort by date
                 .PageBy(input.SkipCount, input.MaxResultCount)
        );

        return new PagedResultDto<AlertHistoryDto>(
            totalCount,
            ObjectMapper.Map<List<AlertHistory>, List<AlertHistoryDto>>(items)
        );
    }

    public async Task<List<AlertHistoryDto>> GetHighConfidenceNotificationsAsync()
    {
        var query = await _alertHistoryRepository.GetQueryableAsync();

        // Get recent high confidence alerts (>= 70)
        var items = await AsyncExecuter.ToListAsync(
            query.Where(x => x.Confidence >= 70 && !x.IsRead)
                 .OrderByDescending(x => x.EmittedAt)
                 .Take(50)
        );

        return ObjectMapper.Map<List<AlertHistory>, List<AlertHistoryDto>>(items);
    }

    public async Task MarkAsReadAsync(Guid id)
    {
        var alert = await _alertHistoryRepository.GetAsync(id);
        alert.IsRead = true;
        await _alertHistoryRepository.UpdateAsync(alert);
    }

    public async Task MarkAllAsReadAsync()
    {
        var query = await _alertHistoryRepository.GetQueryableAsync();
        var unreadItems = await AsyncExecuter.ToListAsync(query.Where(x => !x.IsRead));

        foreach (var item in unreadItems)
        {
            item.IsRead = true;
            await _alertHistoryRepository.UpdateAsync(item);
        }
    }
}
