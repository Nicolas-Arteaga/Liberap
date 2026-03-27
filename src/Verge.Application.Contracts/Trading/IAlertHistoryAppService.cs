using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;
using Volo.Abp.Application.Dtos;
using Verge.Trading.DTOs;

namespace Verge.Trading;

public interface IAlertHistoryAppService : IApplicationService
{
    Task<PagedResultDto<AlertHistoryDto>> GetListAsync(GetAlertHistoryInput input);
    Task<List<AlertHistoryDto>> GetHighConfidenceNotificationsAsync();
    Task MarkAsReadAsync(Guid id);
    Task MarkAllAsReadAsync();
}

public class GetAlertHistoryInput : PagedAndSortedResultRequestDto
{
    public string? Symbol { get; set; }
    public string? Style { get; set; }
    public string? Status { get; set; }
    public bool? IsRead { get; set; }
}
